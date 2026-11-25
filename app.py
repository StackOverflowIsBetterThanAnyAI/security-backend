from flask import Flask, Response, request, jsonify, send_from_directory
from flask_cors import CORS
from waitress import serve
import sqlite3
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from functools import wraps
import math
import os
import re
import subprocess
import threading
import time

import system_stats
from thumbnails import read_thumbnail
from folder_data import (
    IMAGE_FILENAME_PATTERN,
    IMAGE_FOLDER_LOCATION,
    IMAGE_FOLDER_LOCATION_LIVE,
    MAX_ARCHIVE_IMAGES,
)

os.makedirs(IMAGE_FOLDER_LOCATION, exist_ok=True)
os.makedirs(IMAGE_FOLDER_LOCATION_LIVE, exist_ok=True)

load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9]{5,20}$")
PASSWORD_PATTERN = re.compile(r"^[^\s]{8,25}$")

FILENAME_PATTERN = IMAGE_FILENAME_PATTERN
DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
THUMBNAIL_TARGET_SECONDS = 12 * 60 * 60
IMAGE_CACHE_SECONDS = 365 * 24 * 60 * 60

PAGE_SIZE = 36
MAX_PAGE = math.ceil(MAX_ARCHIVE_IMAGES / PAGE_SIZE)

MAX_USERS = 8

# after this many failed logins from one address within the window,
# further logins from it are refused for the lock time
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 5 * 60
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60

POWEROFF_COMMAND = ["/usr/bin/systemctl", "poweroff"]

TOKEN_MAX_AGE_SECONDS = 30 * 24 * 60 * 60

app = Flask(__name__)
CORS(app)


def get_db_connection():
    conn = sqlite3.connect("database.db", timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with sqlite3.connect("database.db", timeout=10, check_same_thread=False) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                token TEXT,
                role TEXT DEFAULT 'user',
                token_created_at INTEGER
            )
        """)

        columns = [row[1] for row in conn.execute("PRAGMA table_info(users)")]
        if "token_created_at" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN token_created_at INTEGER")
        conn.execute(
            "UPDATE users SET token_created_at = ? "
            "WHERE token IS NOT NULL AND token_created_at IS NULL",
            (int(time.time()),),
        )
        conn.commit()

    # === Admin ===
    admin = conn.execute(
        "SELECT * FROM users WHERE name = ?", (ADMIN_USERNAME,)
    ).fetchone()

    if not admin:
        hashed_pw = generate_password_hash(ADMIN_PASSWORD)
        token = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO users (name, password, role, token, token_created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (ADMIN_USERNAME, hashed_pw, "admin", token, int(time.time())),
        )
        conn.commit()


init_db()


# ----------- AUTH DECORATOR -----------
def token_required(role_minimum="member"):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization", "")
            token = header[len("Bearer ") :] if header.startswith("Bearer ") else None

            if not token:
                return jsonify({"error": "Token required"}), 401

            with get_db_connection() as conn:
                user = conn.execute(
                    "SELECT * FROM users WHERE token = ?", (token,)
                ).fetchone()

                if not user:
                    return jsonify({"error": "Invalid token"}), 403

                token_created_at = user["token_created_at"] or 0
                if time.time() - token_created_at > TOKEN_MAX_AGE_SECONDS:
                    conn.execute(
                        "UPDATE users SET token = NULL, token_created_at = NULL "
                        "WHERE id = ?",
                        (user["id"],),
                    )
                    conn.commit()
                    return jsonify({"error": "Token expired"}), 403

            role_hierarchy = {"user": 0, "member": 1, "admin": 2}
            if role_hierarchy[user["role"]] < role_hierarchy[role_minimum]:
                return jsonify({"error": "Insufficient role"}), 403

            return f(user, *args, **kwargs)

        return wrapper

    return decorator


# ============ ROUTES ============


# === Register ===
@app.route("/register", methods=["POST"])
def register():
    data = request.json

    if not data:
        return jsonify({"error": "Invalid request format"}), 400

    name = data.get("name")
    password = data.get("password")

    if not name or not password:
        return jsonify({"error": "Name and password required"}), 400

    if not USERNAME_PATTERN.match(name):
        return (
            jsonify(
                {"error": "Invalid name format. Must be 5-20 alphanumeric characters."}
            ),
            400,
        )

    if not PASSWORD_PATTERN.match(password):
        return (
            jsonify(
                {
                    "error": "Invalid password format. Must be 8-25 characters and contain no spaces."
                }
            ),
            400,
        )

    try:
        with get_db_connection() as conn:
            count_row = conn.execute("SELECT COUNT(id) AS count FROM users").fetchone()
            user_count = count_row["count"]

            if user_count >= MAX_USERS:
                return (
                    jsonify({"error": "Registration limit reached."}),
                    400,
                )
    except sqlite3.OperationalError:
        return jsonify({"error": "Database busy, please retry."}), 500

    role = "user"
    hashed_pw = generate_password_hash(password)
    token = secrets.token_hex(16)

    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO users (name, password, token, role, token_created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (name, hashed_pw, token, role, int(time.time())),
            )
            conn.commit()
        return jsonify({"role": role, "token": token}), 201

    except sqlite3.IntegrityError:
        return jsonify({"error": "User already exists"}), 400

    except sqlite3.OperationalError:
        return jsonify({"error": "Database busy, please retry."}), 500


# === Login ===
login_failures = {}
login_failures_lock = threading.Lock()


def login_locked_seconds(address):
    with login_failures_lock:
        entry = login_failures.get(address)
        if not entry:
            return 0
        return max(0, math.ceil(entry["locked_until"] - time.time()))


def register_login_failure(address):
    now = time.time()
    with login_failures_lock:
        # forget addresses whose window and lock are over, keeps the dict small
        for key in [
            key
            for key, entry in login_failures.items()
            if now - entry["first"] > LOGIN_FAILURE_WINDOW_SECONDS
            and now >= entry["locked_until"]
        ]:
            del login_failures[key]

        entry = login_failures.get(address)
        if not entry or now - entry["first"] > LOGIN_FAILURE_WINDOW_SECONDS:
            entry = {"count": 0, "first": now, "locked_until": 0}
            login_failures[address] = entry
        entry["count"] += 1
        if entry["count"] >= LOGIN_MAX_FAILURES:
            entry["count"] = 0
            entry["first"] = now
            entry["locked_until"] = now + LOGIN_LOCK_SECONDS


def reset_login_failures(address):
    with login_failures_lock:
        login_failures.pop(address, None)


def too_many_attempts(seconds):
    minutes = math.ceil(seconds / 60)
    plural = "" if minutes == 1 else "s"
    response = jsonify(
        {
            "error": "Too many failed login attempts. "
            f"Try again in {minutes} minute{plural}."
        }
    )
    response.headers["Retry-After"] = str(seconds)
    return response, 429


def invalid_credentials(address):
    register_login_failure(address)
    locked = login_locked_seconds(address)
    if locked:
        return too_many_attempts(locked)
    return jsonify({"error": "Invalid credentials"}), 401


@app.route("/login", methods=["POST"])
def login():
    address = request.remote_addr or "unknown"
    locked = login_locked_seconds(address)
    if locked:
        return too_many_attempts(locked)

    data = request.json

    if not data:
        return jsonify({"error": "Invalid request format"}), 400

    name = data.get("name")
    password = data.get("password")

    if not name or not password:
        return invalid_credentials(address)

    if not USERNAME_PATTERN.match(name) or not PASSWORD_PATTERN.match(password):
        return invalid_credentials(address)

    with get_db_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
        if user and check_password_hash(user["password"], password):
            token = secrets.token_hex(16)
            conn.execute(
                "UPDATE users SET token = ?, token_created_at = ? WHERE id = ?",
                (token, int(time.time()), user["id"]),
            )
            conn.commit()
            reset_login_failures(address)
            return jsonify({"role": user["role"], "token": token}), 200

    return invalid_credentials(address)


# === Images ===
@app.route("/images", methods=["GET"])
@token_required(role_minimum="member")
def list_images(current_user):
    page_param = request.args.get("page")
    try:
        page = int(page_param) if page_param is not None else 1
    except ValueError:
        return jsonify({"error": "Page must be a valid integer."}), 400

    if page < 1:
        page = 1

    if page > MAX_PAGE:
        return (
            jsonify({"error": "Page number exceeds the maximum allowed page."}),
            400,
        )

    day = request.args.get("day")
    if day is not None and not DAY_PATTERN.match(day):
        return jsonify({"error": "Day must have the format YYYY-MM-DD."}), 400

    page_size = PAGE_SIZE

    files = list_archive_files()
    if day is not None:
        files = [f for f in files if image_day(f) == day]
    start = (page - 1) * page_size
    end = start + page_size
    paginated = files[start:end]

    image_urls = [f"/image/{f}" for f in paginated]

    return jsonify(
        {
            "images": image_urls,
            "page": page,
            "total_images": len(files),
        }
    )


@app.route("/days", methods=["GET"])
@token_required(role_minimum="member")
def list_days(current_user):
    days = {}
    for f in list_archive_files():
        day = image_day(f)
        distance = abs(image_seconds_of_day(f) - THUMBNAIL_TARGET_SECONDS)
        entry = days.setdefault(day, {"date": day, "count": 0, "distance": None})
        entry["count"] += 1
        if entry["distance"] is None or distance < entry["distance"]:
            entry["distance"] = distance
            entry["thumbnail"] = f"/image/{f}"

    result = [
        {"date": d["date"], "count": d["count"], "thumbnail": d["thumbnail"]}
        for d in sorted(days.values(), key=lambda d: d["date"], reverse=True)
    ]
    return jsonify({"days": result})


def list_archive_files():
    return sorted(
        f for f in os.listdir(IMAGE_FOLDER_LOCATION) if FILENAME_PATTERN.match(f)
    )


def image_day(filename):
    return filename[len("security_image_") : len("security_image_YYYY-MM-DD")]


def image_seconds_of_day(filename):
    time_part = filename[len("security_image_YYYY-MM-DD_") : -len(".jpg")]
    hours, minutes, seconds = (int(v) for v in time_part.split("-"))
    return hours * 3600 + minutes * 60 + seconds


def cache_permanently(response):
    response.cache_control.no_cache = None
    response.cache_control.max_age = IMAGE_CACHE_SECONDS
    response.cache_control.public = False
    response.cache_control.private = True
    response.cache_control.immutable = True
    return response


@app.route("/image/<filename>")
@token_required(role_minimum="member")
def get_image(current_user, filename):
    if not FILENAME_PATTERN.match(filename):
        return jsonify({"error": "Resource not found or invalid format."}), 404

    return cache_permanently(send_from_directory(IMAGE_FOLDER_LOCATION, filename))


@app.route("/thumbnail/<filename>")
@token_required(role_minimum="member")
def get_thumbnail(current_user, filename):
    if not FILENAME_PATTERN.match(filename):
        return jsonify({"error": "Resource not found or invalid format."}), 404

    path = os.path.join(IMAGE_FOLDER_LOCATION, filename)
    if not os.path.isfile(path):
        return jsonify({"error": "Resource not found or invalid format."}), 404

    thumbnail = read_thumbnail(path)
    if thumbnail is None:
        return jsonify({"error": "Resource not found or invalid format."}), 404
    return cache_permanently(Response(thumbnail, mimetype="image/jpeg"))


@app.route("/live")
@token_required(role_minimum="member")
def latest_image(current_user):
    try:
        valid_files = sorted(
            [
                f
                for f in os.listdir(IMAGE_FOLDER_LOCATION_LIVE)
                if FILENAME_PATTERN.match(f)
            ]
        )

        if not valid_files:
            return jsonify({"error": "No valid images found"}), 404

        latest = valid_files[-1]
        response = send_from_directory(IMAGE_FOLDER_LOCATION_LIVE, latest, max_age=0)
        response.headers["X-Image-Name"] = latest
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/live/meta")
@token_required(role_minimum="member")
def latest_image_meta(current_user):
    try:
        latest = get_latest_image_filename()

        if not latest:
            return jsonify({"error": "No valid images found"}), 404

        if not FILENAME_PATTERN.match(latest):
            return jsonify({"error": "Invalid filename format"}), 400

        return jsonify({"filename": latest})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


def get_latest_image_filename():
    valid_files = sorted(
        [f for f in os.listdir(IMAGE_FOLDER_LOCATION_LIVE) if FILENAME_PATTERN.match(f)]
    )
    if not valid_files:
        return None
    return valid_files[-1]


# === Get User Role ===
@app.route("/user/role", methods=["GET"])
@token_required(role_minimum="user")
def get_current_user_role(current_user):
    if not current_user:
        return jsonify({"error": "Invalid request format"}), 400

    return (
        jsonify(
            {
                "role": current_user["role"],
            }
        ),
        200,
    )


# ============ ADMIN ROUTES ============


# === Update User Role ===
@app.route("/user/role", methods=["PATCH"])
@token_required(role_minimum="admin")
def update_user_role(current_user):
    data = request.json

    if not data:
        return jsonify({"error": "Invalid request format"}), 400

    target_id = data.get("id")
    new_role = data.get("role")

    if (
        not isinstance(target_id, int)
        or target_id <= 0
        or new_role not in ["user", "member"]
    ):
        return (
            jsonify({"error": "Missing target ID or invalid role."}),
            400,
        )

    try:
        with get_db_connection() as conn:
            target_user = conn.execute(
                "SELECT id, name, role, token FROM users WHERE id = ?", (target_id,)
            ).fetchone()

            if not target_user:
                return jsonify({"error": "User not found."}), 404

            if target_user["id"] == current_user["id"]:
                return (
                    jsonify({"error": "Cannot change your own role."}),
                    403,
                )

            if target_user["name"] == ADMIN_USERNAME:
                return (
                    jsonify({"error": "Cannot change the role of admin accounts."}),
                    403,
                )

            if target_user["role"] == "admin":
                return (
                    jsonify({"error": "Cannot change the role of admin accounts."}),
                    403,
                )

            old_role = target_user["role"]
            token_for_user = target_user["token"]

            if old_role == "member" and new_role == "user":
                token_for_user = None

            conn.execute(
                "UPDATE users SET role = ?, token = ? WHERE id = ?",
                (new_role, token_for_user, target_id),
            )
            conn.commit()

            return (
                jsonify(
                    {"message": "Role updated successfully. User session invalidated."}
                ),
                200,
            )

    except Exception:
        return jsonify({"error": "Database error."}), 500


# === Delete User ===
@app.route("/user/delete", methods=["DELETE"])
@token_required(role_minimum="admin")
def delete_user(current_user):
    data = request.json

    if not data:
        return jsonify({"error": "Invalid request format"}), 400

    target_id = data.get("id")

    if not isinstance(target_id, int) or target_id <= 0:
        return jsonify({"error": "Missing or invalid target ID."}), 400

    try:
        with get_db_connection() as conn:
            target_user = conn.execute(
                "SELECT id, name, role FROM users WHERE id = ?", (target_id,)
            ).fetchone()

            if not target_user:
                return jsonify({"error": "User not found."}), 404

            if target_user["id"] == current_user["id"]:
                return (
                    jsonify({"error": "Cannot delete your own account."}),
                    400,
                )

            if target_user["name"] == ADMIN_USERNAME:
                return (
                    jsonify({"error": "Cannot delete the primary admin account."}),
                    400,
                )

            if target_user["role"] == "admin":
                return (
                    jsonify({"error": "Cannot delete admin account."}),
                    400,
                )

            cursor = conn.execute(
                "DELETE FROM users WHERE id = ?",
                (target_id,),
            )
            conn.commit()

            if cursor.rowcount > 0:
                return (
                    jsonify({"message": "User successfully deleted."}),
                    200,
                )
            else:
                return (
                    jsonify({"error": "User not found or could not be deleted."}),
                    404,
                )

    except Exception:
        return jsonify({"error": "Database error"}), 500


# === System Stats ===
@app.route("/admin/stats", methods=["GET"])
@token_required(role_minimum="admin")
def get_system_stats(current_user):
    return jsonify(system_stats.collect())


# === Shutdown ===
@app.route("/admin/shutdown", methods=["POST"])
@token_required(role_minimum="admin")
def shutdown_system(current_user):
    try:
        allowed = subprocess.run(
            ["sudo", "-n", "-l", *POWEROFF_COMMAND],
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return jsonify({"error": "Shutdown not available"}), 500
    if allowed.returncode != 0:
        return jsonify({"error": "Shutdown not permitted"}), 500

    # delay the poweroff so the response reaches the app first
    subprocess.Popen(
        ["sh", "-c", f"sleep 2 && sudo -n {' '.join(POWEROFF_COMMAND)}"],
        start_new_session=True,
    )
    return jsonify({"message": "Shutting down"}), 202


# === Get All Users ===
@app.route("/users", methods=["GET"])
@token_required(role_minimum="admin")
def get_users(current_user):
    admin_name = current_user["name"]

    with get_db_connection() as conn:
        users = conn.execute(
            "SELECT id, name, role FROM users WHERE name != ?", (admin_name,)
        ).fetchall()

    return jsonify([dict(user) for user in users])


# ============ START ============

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5000, threads=4)
