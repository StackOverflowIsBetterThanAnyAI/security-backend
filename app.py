from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os

load_dotenv()

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

app = Flask(__name__)
CORS(app)


def get_db_connection():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
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

    conn.close()


init_db()


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
        conn = get_db_connection()
        conn.execute(
            "INSERT INTO users (name, password, token, role) VALUES (?, ?, ?, ?)",
            (name, hashed_pw, token, role),
        )
        conn.commit()
        conn.close()
        return (
            jsonify({"message": "User registered", "token": token, "role": role}),
            201,
        )
    except sqlite3.IntegrityError:
        return jsonify({"error": "User already exists"}), 400


# === Login ===
@app.route("/login", methods=["POST"])
def login():
    data = request.json
    name = data.get("name")
    password = data.get("password")

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE name = ?", (name,)).fetchone()

    if user and check_password_hash(user["password"], password):
        token = secrets.token_hex(16)
        conn.execute("UPDATE users SET token = ? WHERE id = ?", (token, user["id"]))
        conn.commit()
        conn.close()
        return jsonify({"token": token, "role": user["role"]})
    else:
        conn.close()
        return jsonify({"error": "Invalid credentials"}), 401


# === get all users (for testing only) ===
@app.route("/users", methods=["GET"])
def get_users():
    conn = get_db_connection()
    users = conn.execute("SELECT * FROM users").fetchall()
    conn.close()

    users_list = [dict(user) for user in users]
    return jsonify(users_list)


# ============ START ============

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
