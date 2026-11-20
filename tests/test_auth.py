import os
import re
import tempfile
import unittest
from pathlib import Path


TEST_DIRECTORY = tempfile.TemporaryDirectory()
os.environ["DATABASE_PATH"] = str(Path(TEST_DIRECTORY.name) / "test.db")
os.environ["UPLOAD_FOLDER"] = str(Path(TEST_DIRECTORY.name) / "uploads")
os.environ.pop("APP_ENV", None)

import app as social_app
from werkzeug.security import check_password_hash


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        social_app.app.config.update(TESTING=True)
        self.client = social_app.app.test_client()

    def csrf_from_page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def create_account(self, username="new_user", password="correct-horse-battery"):
        token = self.csrf_from_page("/register")
        return self.client.post(
            "/register",
            data={"csrf_token": token, "username": username, "password": password},
        )

    def api_session(self):
        response = self.client.get("/api/session")
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_feed_and_api_require_login(self):
        self.assertEqual(self.client.get("/").status_code, 302)
        self.assertEqual(self.client.get("/api/posts").status_code, 401)

    def test_registration_hashes_password_and_logs_user_in(self):
        response = self.create_account()
        self.assertEqual(response.status_code, 302)
        user = self.api_session()["user"]
        connection = social_app.get_db_connection()
        try:
            row = connection.execute(
                "SELECT password_hash FROM Users WHERE user_id = ?", (user["user_id"],)
            ).fetchone()
        finally:
            connection.close()
        self.assertNotEqual(row["password_hash"], "correct-horse-battery")
        self.assertTrue(check_password_hash(row["password_hash"], "correct-horse-battery"))

    def test_api_mutations_require_csrf_and_use_session_identity(self):
        self.create_account(username="post_owner")
        session_data = self.api_session()
        post_id = self.client.get("/api/posts").json[0]["post_id"]

        rejected = self.client.post(
            f"/api/posts/{post_id}/like", json={}, headers={"X-CSRF-Token": "invalid"}
        )
        self.assertEqual(rejected.status_code, 400)
        accepted = self.client.post(
            f"/api/posts/{post_id}/like",
            json={"user_id": 1},
            headers={"X-CSRF-Token": session_data["csrf_token"]},
        )
        self.assertEqual(accepted.status_code, 200)
        connection = social_app.get_db_connection()
        try:
            like = connection.execute(
                "SELECT user_id FROM Likes WHERE post_id = ?", (post_id,)
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(like["user_id"], session_data["user"]["user_id"])

    def test_login_rejects_bad_password_and_limits_repeated_attempts(self):
        self.create_account(username="lockout_user")
        self.client.post("/logout", data={"csrf_token": self.api_session()["csrf_token"]})
        token = self.csrf_from_page("/login")
        for attempt in range(5):
            response = self.client.post(
                "/login",
                data={"csrf_token": token, "username": "lockout_user", "password": "wrong"},
                environ_base={"REMOTE_ADDR": "192.0.2.45"},
            )
            self.assertEqual(response.status_code, 401, f"attempt {attempt + 1}")
        locked = self.client.post(
            "/login",
            data={"csrf_token": token, "username": "lockout_user", "password": "wrong"},
            environ_base={"REMOTE_ADDR": "192.0.2.45"},
        )
        self.assertEqual(locked.status_code, 429)

    def test_logout_clears_session(self):
        self.create_account(username="logout_user")
        token = self.api_session()["csrf_token"]
        response = self.client.post("/logout", data={"csrf_token": token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/api/session").status_code, 401)


if __name__ == "__main__":
    unittest.main()
