# Little Moments

A beginner-friendly social feed built with Flask, HTML, CSS, JavaScript, and SQLite. Users can register, sign in, share photos, like posts, comment, and browse profiles. This is a learning project and is not production-ready.

## Project files

```text
social-site/
├── app.py                       # Flask pages, authentication, API, and SQLite setup
├── netlify.toml                 # Netlify static publish directory and preview routes
├── requirements.txt             # Python dependencies
├── database/
│   └── social_media.db          # Created automatically when the app starts
├── templates/
│   ├── index.html               # Feed and create-post form
│   ├── login.html               # Sign-in form
│   ├── profile.html             # User profile page
│   └── register.html            # Account creation form
├── static/
    ├── css/style.css            # Responsive page styling
    ├── js/app.js                # Feed, likes, comments, and post form
    ├── js/profile.js            # Profile data and profile interactions
│   └── uploads/                 # Demo illustrations, avatars, and local uploads
├── netlify-public/              # Sanitized static preview; no local user uploads
└── tests/
    └── test_auth.py             # Authentication, CSRF, and session tests
```

The database has `Users`, `Posts`, `Likes`, `Comments`, and `LoginAttempts` tables. A new local database includes three sample accounts and posts. In production mode, the app does not seed the sample accounts. The local database and uploaded files are ignored by Git.

## Run locally in VS Code

1. Install Python 3.9 or newer and open this project folder in VS Code.
2. Open **Terminal → New Terminal**.
3. Create and activate a virtual environment:

   **Windows PowerShell**
   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   **Windows Command Prompt**
   ```bat
   py -m venv .venv
   .\.venv\Scripts\activate.bat
   ```

   If PowerShell blocks activation, use the Command Prompt instructions or run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal.

4. Install Flask:
   ```powershell
   python -m pip install -r requirements.txt
   ```
5. Start the website:
   ```powershell
   python app.py
   ```
6. Open the local address printed in the terminal (usually `http://127.0.0.1:5000`).
7. Stop the server with **Ctrl+C** in the terminal.

Run the authentication tests with:
```powershell
python -m unittest discover -s tests -v
```

### Sample sign-in

The local sample accounts are `maya`, `leo`, and `amina`. Their local-only sample password is `MomentDemo2026!`. You can also create a new account from the registration page. Never use the sample password or sample accounts for a public deployment.

## Authentication and safety notes

- Passwords are stored as Werkzeug password hashes, never as plain text.
- New passwords must be 12–128 characters. Usernames are 3–20 letters, numbers, or underscores.
- The signed session cookie is HTTP-only and `SameSite=Lax`; it expires after 12 hours. Production mode also marks it `Secure`.
- Sign-in and registration forms use signed, two-hour CSRF tokens; authenticated API mutations use session-bound CSRF tokens. Five failed sign-ins from one IP hash trigger a 15-minute lockout.
- Database access uses parameterized SQL. User text is rendered as text, not HTML.
- Uploads are limited to PNG, JPG/JPEG, GIF, or WEBP images, checked against their file signatures, and capped at 5 MB.
- The app is still a learning example; it lacks production features such as email verification, password recovery, account moderation, and a multi-instance rate-limit service.

## How the parts connect

Flask serves `templates/index.html`, `templates/login.html`, `templates/register.html`, and `templates/profile.html`. The templates load CSS and JavaScript from `static/`. The browser JavaScript uses `fetch()` and the signed-in session cookie to call `/api/...` endpoints. Mutating API requests also send the session CSRF token in `X-CSRF-Token`.

The API validates requests and uses parameterized SQL against `database/social_media.db`. When a post is submitted, the browser sends its caption and image as `FormData`; Flask validates the file, saves it under `static/uploads/`, and saves its generated filename and caption in SQLite. The page then retrieves posts, likes, and comments as JSON. Uploaded media is served through an authenticated Flask route.

## API overview

| Method | URL | Purpose |
| --- | --- | --- |
| `GET` / `POST` | `/login` | Sign in |
| `GET` / `POST` | `/register` | Create an account and sign in |
| `POST` | `/logout` | Sign out |
| `GET` | `/api/session` | Get the signed-in user and API CSRF token |
| `GET` | `/api/users/<id>` | Get a profile and post count |
| `GET` | `/api/users/<id>/posts` | Get a user's posts |
| `GET` | `/api/posts` | Get the feed |
| `POST` | `/api/posts` | Save an image and create a post (multipart form) |
| `POST` | `/api/posts/<id>/like` | Like a post |
| `DELETE` | `/api/posts/<id>/like` | Unlike a post |
| `GET` | `/api/posts/<id>/comments` | Get a post's comments |
| `POST` | `/api/posts/<id>/comments` | Add a comment (JSON) |

Feed, profile, and media endpoints require a signed-in session. The server takes the acting user from that session; clients cannot choose another user's ID for likes or comments.

## Netlify static preview

The Netlify site is an explicitly static visual preview. Its sign-in and registration pages do not accept passwords; feed actions are disabled. The working authenticated app remains the Flask version described above. Netlify serves the curated `netlify-public/` directory, so local database records and uploaded user photos are not published.

To publish the static preview, connect the GitHub repository to Netlify and use the `main` branch. Netlify detects the publish folder from `netlify.toml`; no build command is needed. Alternatively, install and sign in to the Netlify CLI, then run `netlify deploy --prod --dir netlify-public`.

To deploy the complete app instead, use a Python host with persistent storage for both `DATABASE_PATH` and `UPLOAD_FOLDER`, configure `APP_ENV=production` and a long random `FLASK_SECRET_KEY`, and serve Flask with a production WSGI server. Do not commit the SQLite database, uploaded user files, or secret key. A static Netlify deploy does not run Flask and cannot provide persistent SQLite or uploaded files.

## Debug common issues

- **`ModuleNotFoundError: No module named 'flask'`**: activate `.venv` and run `python -m pip install -r requirements.txt`.
- **`py` or `python` is not recognized**: install Python from python.org and enable the option to add Python to PATH; restart the VS Code terminal.
- **PowerShell says script execution is disabled**: use the Command Prompt activation command above, or set the process-only policy shown in step 3.
- **Sign-in says credentials are wrong**: check the spelling, use the local sample password above for the three sample users, or register an account.
- **Sign-in is temporarily locked**: wait 15 minutes after five failed attempts from the same IP address.
- **Image upload is rejected**: use a real PNG, JPG/JPEG, GIF, or WEBP image no larger than 5 MB. Renaming another file to an image extension is not enough.
- **A template or static file is missing**: check that folder/file names match the project structure, then restart Flask and refresh the browser.
- **Feed or database error**: check the VS Code terminal for the Flask traceback. The SQLite database is generated at `database/social_media.db`. Stop the server before deleting it to reset the local sample data; uploaded files are not automatically deleted.

The Flask debug server is intended only for local development. Do not expose it directly to the internet.
