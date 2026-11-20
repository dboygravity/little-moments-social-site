import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = Path(os.environ.get("DATABASE_PATH", BASE_DIR / "database" / "social_media.db"))
DATABASE_DIR = DATABASE_PATH.parent
UPLOAD_FOLDER = Path(os.environ.get("UPLOAD_FOLDER", BASE_DIR / "static" / "uploads"))
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=(
        os.environ.get("COOKIE_SECURE", "").lower() == "true"
        or os.environ.get("APP_ENV") == "production"
    ),
    PERMANENT_SESSION_LIFETIME=60 * 60 * 12,
)
app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_SIZE + 64 * 1024
if os.environ.get("APP_ENV") == "production" and not os.environ.get("FLASK_SECRET_KEY"):
    raise RuntimeError("Set FLASK_SECRET_KEY to a long, random value in production.")

DEMO_PASSWORD = "MomentDemo2026!"
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60
DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))


def csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def auth_form_csrf_token():
    issued_at = int(datetime.now(timezone.utc).timestamp())
    nonce = secrets.token_urlsafe(18)
    payload = f"{issued_at}.{nonce}"
    signature = hmac.new(
        app.secret_key.encode("utf-8"),
        f"auth-form:{payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


app.jinja_env.globals["csrf_token"] = csrf_token
app.jinja_env.globals["auth_form_csrf_token"] = auth_form_csrf_token


def get_db_connection():
    """Open a database connection that returns rows by column name."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    DATABASE_DIR.mkdir(exist_ok=True)
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
    connection = get_db_connection()
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS Users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                profile_picture TEXT NOT NULL,
                password_hash TEXT
            );

            CREATE TABLE IF NOT EXISTS Posts (
                post_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                image TEXT NOT NULL,
                caption TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES Users(user_id)
            );

            CREATE TABLE IF NOT EXISTS Likes (
                like_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                UNIQUE (post_id, user_id),
                FOREIGN KEY (post_id) REFERENCES Posts(post_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS Comments (
                comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                comment TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (post_id) REFERENCES Posts(post_id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES Users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS LoginAttempts (
                ip_hash TEXT PRIMARY KEY,
                failed_count INTEGER NOT NULL,
                window_started REAL NOT NULL,
                locked_until REAL NOT NULL DEFAULT 0
            );
            """
        )

        user_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(Users)")
        }
        if "password_hash" not in user_columns:
            connection.execute("ALTER TABLE Users ADD COLUMN password_hash TEXT")

        user_count = connection.execute(
            "SELECT COUNT(*) FROM Users"
        ).fetchone()[0]
        if user_count == 0 and os.environ.get("APP_ENV") != "production":
            connection.executemany(
                "INSERT INTO Users (username, profile_picture, password_hash) VALUES (?, ?, ?)",
                [
                    ("maya", "avatar-maya.svg", generate_password_hash(DEMO_PASSWORD)),
                    ("leo", "avatar-leo.svg", generate_password_hash(DEMO_PASSWORD)),
                    ("amina", "avatar-amina.svg", generate_password_hash(DEMO_PASSWORD)),
                ],
            )
            sample_posts = [
                (1, "sample-coffee.svg", "Slow mornings and good coffee ☕"),
                (2, "sample-coast.svg", "A little fresh air goes a long way."),
                (3, "sample-flowers.svg", "Found some color on my walk today 🌼"),
            ]
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            connection.executemany(
                "INSERT INTO Posts (user_id, image, caption, created_at) "
                "VALUES (?, ?, ?, ?)",
                [(user_id, image, caption, created_at) for user_id, image, caption in sample_posts],
            )
        elif os.environ.get("APP_ENV") != "production":
            connection.execute(
                "UPDATE Users SET password_hash = ? WHERE password_hash IS NULL",
                (generate_password_hash(DEMO_PASSWORD),),
            )
        connection.commit()
    finally:
        connection.close()


def image_signature_matches(extension, content):
    """Check that the uploaded file contents match one of the allowed formats."""
    if extension == "png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {"jpg", "jpeg"}:
        return content.startswith(b"\xff\xd8\xff")
    if extension == "gif":
        return content.startswith((b"GIF87a", b"GIF89a"))
    if extension == "webp":
        return len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


def allowed_image(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def valid_user(connection, user_id):
    return connection.execute(
        "SELECT user_id FROM Users WHERE user_id = ?", (user_id,)
    ).fetchone()


def post_to_dict(row):
    return {
        "post_id": row["post_id"],
        "user_id": row["user_id"],
        "username": row["username"],
        "profile_picture": row["profile_picture"],
        "image": row["image"],
        "caption": row["caption"],
        "created_at": row["created_at"],
        "like_count": row["like_count"],
        "comment_count": row["comment_count"],
        "liked_by_me": bool(row["liked_by_me"]),
    }


def fetch_posts(connection, current_user_id, user_id=None):
    query = """
        SELECT Posts.post_id, Posts.user_id, Users.username, Users.profile_picture,
               Posts.image, Posts.caption, Posts.created_at,
               (SELECT COUNT(*) FROM Likes WHERE Likes.post_id = Posts.post_id) AS like_count,
               (SELECT COUNT(*) FROM Comments WHERE Comments.post_id = Posts.post_id) AS comment_count,
               EXISTS (
                   SELECT 1 FROM Likes
                   WHERE Likes.post_id = Posts.post_id AND Likes.user_id = ?
               ) AS liked_by_me
        FROM Posts
        JOIN Users ON Users.user_id = Posts.user_id
    """
    parameters = [current_user_id]
    if user_id is not None:
        query += " WHERE Posts.user_id = ?"
        parameters.append(user_id)
    query += " ORDER BY Posts.created_at DESC, Posts.post_id DESC"
    return [post_to_dict(row) for row in connection.execute(query, parameters).fetchall()]


def request_ip_hash():
    return hmac.new(
        app.secret_key.encode("utf-8"),
        request.remote_addr.encode("utf-8") if request.remote_addr else b"unknown",
        hashlib.sha256,
    ).hexdigest()


def login_is_locked(connection, ip_hash, now):
    row = connection.execute(
        "SELECT locked_until FROM LoginAttempts WHERE ip_hash = ?", (ip_hash,)
    ).fetchone()
    return row is not None and row["locked_until"] > now


def record_login_failure(connection, ip_hash, now):
    row = connection.execute(
        "SELECT failed_count, window_started FROM LoginAttempts WHERE ip_hash = ?",
        (ip_hash,),
    ).fetchone()
    if row is None or now - row["window_started"] >= LOCKOUT_SECONDS:
        failed_count = 1
        window_started = now
    else:
        failed_count = row["failed_count"] + 1
        window_started = row["window_started"]
    locked_until = now + LOCKOUT_SECONDS if failed_count >= MAX_LOGIN_ATTEMPTS else 0
    connection.execute(
        """
        INSERT INTO LoginAttempts (ip_hash, failed_count, window_started, locked_until)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(ip_hash) DO UPDATE SET
            failed_count = excluded.failed_count,
            window_started = excluded.window_started,
            locked_until = excluded.locked_until
        """,
        (ip_hash, failed_count, window_started, locked_until),
    )
    connection.commit()


def reset_login_failures(connection, ip_hash):
    connection.execute("DELETE FROM LoginAttempts WHERE ip_hash = ?", (ip_hash,))
    connection.commit()


def csrf_is_valid(token):
    expected = session.get("csrf_token", "")
    return isinstance(token, str) and bool(expected) and hmac.compare_digest(token, expected)


def auth_form_csrf_is_valid(token):
    if not isinstance(token, str):
        return False
    try:
        issued_at, nonce, signature = token.split(".", 2)
        issued_at = int(issued_at)
    except (ValueError, TypeError):
        return False
    now = int(datetime.now(timezone.utc).timestamp())
    if not nonce or abs(now - issued_at) > 2 * 60 * 60:
        return False
    payload = f"{issued_at}.{nonce}"
    expected = hmac.new(
        app.secret_key.encode("utf-8"),
        f"auth-form:{payload}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


@app.before_request
def enforce_login_and_api_csrf():
    if request.endpoint in {"login", "login_submit", "register", "register_submit", "static"}:
        return None

    user_id = session.get("user_id")
    connection = get_db_connection()
    try:
        authenticated = user_id is not None and valid_user(connection, user_id)
    finally:
        connection.close()

    if not authenticated:
        session.clear()
        if request.path.startswith("/api/"):
            return jsonify({"error": "Please sign in to continue."}), 401
        return redirect(url_for("login"))

    if request.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if not csrf_is_valid(request.headers.get("X-CSRF-Token")):
            return jsonify({"error": "Your session token expired. Refresh the page and try again."}), 400
    return None


@app.after_request
def add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; connect-src 'self'; base-uri 'self'; frame-ancestors 'none'",
    )
    return response


@app.get("/login")
def login():
    if session.get("user_id"):
        return redirect(url_for("home"))
    csrf_token()
    return render_template("login.html", error=None)


@app.post("/login")
def login_submit():
    if not auth_form_csrf_is_valid(request.form.get("csrf_token")):
        return render_template(
            "login.html", error="This form expired. Please refresh and try again."
        ), 400
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    ip_hash = request_ip_hash()
    now = datetime.now(timezone.utc).timestamp()
    connection = get_db_connection()
    try:
        if login_is_locked(connection, ip_hash, now):
            return render_template(
                "login.html",
                error="Too many sign-in attempts. Please wait 15 minutes before trying again.",
            ), 429
        user = connection.execute(
            "SELECT user_id, password_hash FROM Users WHERE username = ?", (username,)
        ).fetchone()
        password_hash = user["password_hash"] if user and user["password_hash"] else DUMMY_PASSWORD_HASH
        valid_password = (
            check_password_hash(password_hash, password)
            if len(password) <= 128
            else False
        )
        if user is None or user["password_hash"] is None or not valid_password:
            record_login_failure(connection, ip_hash, now)
            return render_template(
                "login.html", error="Username or password is incorrect."
            ), 401
        reset_login_failures(connection, ip_hash)
        session.clear()
        session["user_id"] = user["user_id"]
        session["csrf_token"] = secrets.token_urlsafe(32)
        session.permanent = True
    finally:
        connection.close()
    return redirect(url_for("home"))


@app.get("/register")
def register():
    if session.get("user_id"):
        return redirect(url_for("home"))
    csrf_token()
    return render_template("register.html", error=None)


@app.post("/register")
def register_submit():
    csrf_token_value = request.form.get("csrf_token")
    if not auth_form_csrf_is_valid(csrf_token_value):
        return render_template(
            "register.html", error="This form expired. Please refresh and try again."
        ), 400
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    if not re.fullmatch(r"[a-z0-9_]{3,20}", username):
        return render_template(
            "register.html",
            error="Username must be 3–20 characters using letters, numbers, or underscores.",
        ), 400
    if len(password) < 12 or len(password) > 128:
        return render_template(
            "register.html", error="Choose a password between 12 and 128 characters."
        ), 400

    connection = get_db_connection()
    try:
        cursor = connection.execute(
            "INSERT INTO Users (username, profile_picture, password_hash) VALUES (?, ?, ?)",
            (username, "avatar-maya.svg", generate_password_hash(password)),
        )
        connection.commit()
        user_id = cursor.lastrowid
    except sqlite3.IntegrityError:
        return render_template(
            "register.html", error="That username is already taken. Please choose another."
        ), 400
    finally:
        connection.close()

    session.clear()
    session["user_id"] = user_id
    session["csrf_token"] = secrets.token_urlsafe(32)
    session.permanent = True
    return redirect(url_for("home"))


@app.post("/logout")
def logout():
    if not csrf_is_valid(request.form.get("csrf_token")):
        return "Your session token expired. Refresh the page and try again.", 400
    session.clear()
    return redirect(url_for("login"))


@app.get("/api/session")
def get_session():
    connection = get_db_connection()
    try:
        user = connection.execute(
            "SELECT user_id, username, profile_picture FROM Users WHERE user_id = ?",
            (session["user_id"],),
        ).fetchone()
        return jsonify({"user": dict(user), "csrf_token": csrf_token()})
    finally:
        connection.close()


@app.get("/")
def home():
    return render_template("index.html")


@app.get("/media/<path:filename>")
def uploaded_media(filename):
    try:
        return send_from_directory(UPLOAD_FOLDER, filename)
    except FileNotFoundError:
        abort(404)


@app.get("/profile/<int:user_id>")
def profile_page(user_id):
    return render_template("profile.html", profile_user_id=user_id)


@app.get("/api/users/<int:user_id>")
def get_user(user_id):
    connection = get_db_connection()
    try:
        user = connection.execute(
            """
            SELECT Users.user_id, Users.username, Users.profile_picture,
                   (SELECT COUNT(*) FROM Posts WHERE Posts.user_id = Users.user_id) AS post_count
            FROM Users WHERE Users.user_id = ?
            """,
            (user_id,),
        ).fetchone()
        if user is None:
            return jsonify({"error": "User not found."}), 404
        return jsonify(dict(user))
    finally:
        connection.close()


@app.get("/api/users/<int:user_id>/posts")
def get_user_posts(user_id):
    connection = get_db_connection()
    try:
        if not valid_user(connection, user_id):
            return jsonify({"error": "User not found."}), 404
        return jsonify(fetch_posts(connection, session["user_id"], user_id))
    finally:
        connection.close()


@app.get("/api/posts")
def get_posts():
    connection = get_db_connection()
    try:
        return jsonify(fetch_posts(connection, session["user_id"]))
    finally:
        connection.close()


@app.post("/api/posts")
def create_post():
    caption = request.form.get("caption", "").strip()
    if not caption:
        return jsonify({"error": "Please write a caption."}), 400
    if len(caption) > 500:
        return jsonify({"error": "Captions must be 500 characters or fewer."}), 400

    image = request.files.get("image")
    if image is None or not image.filename:
        return jsonify({"error": "Please choose an image."}), 400
    if not allowed_image(image.filename):
        return jsonify({"error": "Choose a PNG, JPG, JPEG, GIF, or WEBP image."}), 400

    extension = image.filename.rsplit(".", 1)[1].lower()
    image_content = image.read(MAX_IMAGE_SIZE + 1)
    if len(image_content) > MAX_IMAGE_SIZE:
        return jsonify({"error": "The image must be 5 MB or smaller."}), 413
    if not image_signature_matches(extension, image_content):
        return jsonify({"error": "The file contents do not match a supported image format."}), 400

    user_id = session["user_id"]
    safe_original_name = secure_filename(image.filename)
    if not safe_original_name:
        return jsonify({"error": "Please choose a valid image filename."}), 400

    stored_filename = f"{uuid.uuid4().hex}.{extension}"
    destination = UPLOAD_FOLDER / stored_filename
    destination.write_bytes(image_content)

    connection = get_db_connection()
    try:
        if not valid_user(connection, user_id):
            destination.unlink(missing_ok=True)
            return jsonify({"error": "User not found."}), 404
        cursor = connection.execute(
            "INSERT INTO Posts (user_id, image, caption, created_at) VALUES (?, ?, ?, ?)",
            (user_id, stored_filename, caption, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        connection.commit()
        post_id = cursor.lastrowid
    except sqlite3.Error:
        destination.unlink(missing_ok=True)
        raise
    finally:
        connection.close()

    return jsonify({"message": "Post created.", "post_id": post_id}), 201


@app.post("/api/posts/<int:post_id>/like")
def like_post(post_id):
    user_id = session["user_id"]
    connection = get_db_connection()
    try:
        if not valid_user(connection, user_id):
            return jsonify({"error": "User not found."}), 404
        if not connection.execute(
            "SELECT post_id FROM Posts WHERE post_id = ?", (post_id,)
        ).fetchone():
            return jsonify({"error": "Post not found."}), 404
        connection.execute(
            "INSERT OR IGNORE INTO Likes (post_id, user_id) VALUES (?, ?)",
            (post_id, user_id),
        )
        connection.commit()
        count = connection.execute(
            "SELECT COUNT(*) FROM Likes WHERE post_id = ?", (post_id,)
        ).fetchone()[0]
        return jsonify({"liked": True, "like_count": count})
    finally:
        connection.close()


@app.delete("/api/posts/<int:post_id>/like")
def unlike_post(post_id):
    user_id = session["user_id"]
    connection = get_db_connection()
    try:
        if not valid_user(connection, user_id):
            return jsonify({"error": "User not found."}), 404
        if not connection.execute(
            "SELECT post_id FROM Posts WHERE post_id = ?", (post_id,)
        ).fetchone():
            return jsonify({"error": "Post not found."}), 404
        connection.execute(
            "DELETE FROM Likes WHERE post_id = ? AND user_id = ?", (post_id, user_id)
        )
        connection.commit()
        count = connection.execute(
            "SELECT COUNT(*) FROM Likes WHERE post_id = ?", (post_id,)
        ).fetchone()[0]
        return jsonify({"liked": False, "like_count": count})
    finally:
        connection.close()


@app.get("/api/posts/<int:post_id>/comments")
def get_comments(post_id):
    connection = get_db_connection()
    try:
        if not connection.execute(
            "SELECT post_id FROM Posts WHERE post_id = ?", (post_id,)
        ).fetchone():
            return jsonify({"error": "Post not found."}), 404
        comments = connection.execute(
            """
            SELECT Comments.comment_id, Comments.user_id, Users.username,
                   Users.profile_picture, Comments.comment, Comments.created_at
            FROM Comments JOIN Users ON Users.user_id = Comments.user_id
            WHERE Comments.post_id = ?
            ORDER BY Comments.created_at, Comments.comment_id
            """,
            (post_id,),
        ).fetchall()
        return jsonify([dict(comment) for comment in comments])
    finally:
        connection.close()


@app.post("/api/posts/<int:post_id>/comments")
def add_comment(post_id):
    payload = request.get_json(silent=True) or {}
    comment_text = payload.get("comment", "")
    if not isinstance(comment_text, str) or not comment_text.strip():
        return jsonify({"error": "Please write a comment."}), 400
    comment_text = comment_text.strip()
    if len(comment_text) > 300:
        return jsonify({"error": "Comments must be 300 characters or fewer."}), 400
    user_id = session["user_id"]

    connection = get_db_connection()
    try:
        if not valid_user(connection, user_id):
            return jsonify({"error": "User not found."}), 404
        if not connection.execute(
            "SELECT post_id FROM Posts WHERE post_id = ?", (post_id,)
        ).fetchone():
            return jsonify({"error": "Post not found."}), 404
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cursor = connection.execute(
            "INSERT INTO Comments (post_id, user_id, comment, created_at) VALUES (?, ?, ?, ?)",
            (post_id, user_id, comment_text, created_at),
        )
        connection.commit()
        result = connection.execute(
            """
            SELECT Comments.comment_id, Comments.user_id, Users.username,
                   Users.profile_picture, Comments.comment, Comments.created_at
            FROM Comments JOIN Users ON Users.user_id = Comments.user_id
            WHERE Comments.comment_id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        count = connection.execute(
            "SELECT COUNT(*) FROM Comments WHERE post_id = ?", (post_id,)
        ).fetchone()[0]
        return jsonify({"comment": dict(result), "comment_count": count}), 201
    finally:
        connection.close()


@app.errorhandler(413)
def request_entity_too_large(_error):
    return jsonify({"error": "The image must be 5 MB or smaller."}), 413


@app.context_processor
def add_asset_url_helper():
    return {"avatar_url": lambda filename: url_for("uploaded_media", filename=filename)}


initialize_database()


if __name__ == "__main__":
    app.run(debug=True)
