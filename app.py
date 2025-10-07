from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from functools import wraps
import os

from folder_data import IMAGE_FOLDER_LOCATION


load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

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
    name = data.get("name")
    password = data.get("password")

    if not name or not password:
        return jsonify({"error": "Name and password required"}), 400

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

    except sqlite3.OperationalError as e:
        return jsonify({"error": f"Database busy, please retry. ({str(e)})"}), 500


# === Login ===
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    name = data.get("name")
    password = data.get("password")

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
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 36))

    files = sorted([f for f in os.listdir(IMAGE_FOLDER_LOCATION)])
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
    return send_from_directory(IMAGE_FOLDER_LOCATION, filename)


# === get all users (for testing only) ===
@app.route("/users", methods=["GET"])
def get_users():
    with get_db_connection() as conn:
        users = conn.execute("SELECT * FROM users").fetchall()
    return jsonify([dict(user) for user in users])


# ============ START ============

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
