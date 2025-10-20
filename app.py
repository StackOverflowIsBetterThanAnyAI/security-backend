from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from functools import wraps
import os
import re

from folder_data import IMAGE_FOLDER_LOCATION, IMAGE_FOLDER_LOCATION_LIVE


load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9]{5,20}$")
PASSWORD_PATTERN = re.compile(r"^[^\s]{8,25}$")

FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-]+?\.jpg$")

PAGE_SIZE = 36
MAX_PAGE = 56

MAX_USERS = 8

app = Flask(__name__)
CORS(app)


def get_db_connection():
    conn = sqlite3.connect("database.db", timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with sqlite3.connect("database.db", timeout=10, check_same_thread=False) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                token TEXT,
                role TEXT DEFAULT 'user'
            )
        """
        )
        conn.commit()

    # === Admin ===
    admin = conn.execute(
        "SELECT * FROM users WHERE name = ?", (ADMIN_USERNAME,)
    ).fetchone()

    if not admin:
        from werkzeug.security import generate_password_hash

        hashed_pw = generate_password_hash(ADMIN_PASSWORD)
        token = secrets.token_hex(16)
        conn.execute(
            "INSERT INTO users (name, password, role, token) VALUES (?, ?, ?, ?)",
            (ADMIN_USERNAME, hashed_pw, "admin", token),
        )
        conn.commit()


init_db()


# ----------- AUTH DECORATOR -----------
def token_required(role_minimum="member"):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = request.headers.get("Authorization")
            if token and token.startswith("Bearer "):
                token = token.replace("Bearer ", "")
            else:
                token = request.args.get("token")

            if not token:
                return jsonify({"error": "Token required"}), 401

            with get_db_connection() as conn:
                user = conn.execute(
                    "SELECT * FROM users WHERE token = ?", (token,)
                ).fetchone()

            if not user:
                return jsonify({"error": "Invalid token"}), 403

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
                "INSERT INTO users (name, password, token, role) VALUES (?, ?, ?, ?)",
                (name, hashed_pw, token, role),
            )
            conn.commit()
        return jsonify({"role": role, "token": token}), 201

    except sqlite3.IntegrityError:
        return jsonify({"error": "User already exists"}), 400

    except sqlite3.OperationalError:
        return jsonify({"error": "Database busy, please retry."}), 500


# === Login ===
@app.route("/login", methods=["POST"])
def login():
    data = request.json

    if not data:
        return jsonify({"error": "Invalid request format"}), 400

    name = data.get("name")
    password = data.get("password")

    if not name or not password:
        return jsonify({"error": "Invalid credentials"}), 401

    if not USERNAME_PATTERN.match(name) or not PASSWORD_PATTERN.match(password):
        return jsonify({"error": "Invalid credentials"}), 401

    with get_db_connection() as conn:
        user = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()
        if user and check_password_hash(user["password"], password):
            token = secrets.token_hex(16)
            conn.execute("UPDATE users SET token = ? WHERE id = ?", (token, user["id"]))
            conn.commit()
            return jsonify({"role": user["role"], "token": token}), 200
        else:
            return jsonify({"error": "Invalid credentials"}), 401


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

    page_size = PAGE_SIZE

    all_files = os.listdir(IMAGE_FOLDER_LOCATION)
    valid_files = [f for f in all_files if FILENAME_PATTERN.match(f)]
    files = sorted(valid_files)
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


@app.route("/image/<filename>")
@token_required(role_minimum="member")
def get_image(current_user, filename):
    if not FILENAME_PATTERN.match(filename):
        return jsonify({"error": "Resource not found or invalid format."}), 404

    return send_from_directory(IMAGE_FOLDER_LOCATION, filename)


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
        return send_from_directory(IMAGE_FOLDER_LOCATION_LIVE, latest, max_age=0)

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
                "SELECT * FROM users WHERE id = ?", (target_id,)
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

            conn.execute(
                "UPDATE users SET role = ?, token = NULL WHERE id = ?",
                (new_role, target_id),
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
    app.run(debug=True, host="0.0.0.0", port=5000)
