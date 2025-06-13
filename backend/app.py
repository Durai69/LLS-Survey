from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from sqlalchemy.orm import Session
from flask_jwt_extended import (
    create_access_token, JWTManager, jwt_required, get_jwt_identity,
    unset_jwt_cookies, set_access_cookies
)
from datetime import timedelta
import os
import secrets
import logging

# --- Logging configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from security import verify_password, get_frontend_role, hash_password
from database import SessionLocal
from models import User, Department

# --- Import your blueprints ---
from routes.user_routes import user_bp
from routes.permission_routes import permission_bp
from routes.survey_routes import survey_bp

app = Flask(__name__)

# --- App/Secret Configuration ---
app.secret_key = os.getenv("FLASK_SECRET_KEY", "another_super_secret_key_for_flask_CHANGE_THIS")
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "your_super_secret_jwt_key_CHANGE_THIS_IN_PRODUCTION")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_COOKIE_SECURE"] = False  # Set to True in production
app.config["JWT_COOKIE_CSRF_PROTECT"] = False  # True for production, False for local dev
app.config["JWT_ACCESS_TOKEN_NAME"] = "access_token_cookie"
app.config["JWT_COOKIE_DOMAIN"] = "localhost"  # Use your domain in production
app.config["JWT_COOKIE_PATH"] = "/"

jwt = JWTManager(app)

# --- CORS configuration ---
CORS(
    app,
    resources={r"/*": {"origins": [
        "http://localhost:8080",
        "http://localhost:8081",
        "http://localhost:5173"
    ]}},
    supports_credentials=True
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Auth Routes ---
@app.route("/login", methods=["POST"])
def login():
    db: Session = next(get_db())
    username = request.json.get("username", None)
    password = request.json.get("password", None)
    logger.info(f"Login attempt for username: {username}")

    user = db.query(User).filter(User.username == username).first()
    if user and verify_password(password, user.hashed_password):
        user_data = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "department": user.department,
            "role": get_frontend_role(user.role),
            "is_active": getattr(user, "is_active", True)
        }
        access_token = create_access_token(identity=user.username)
        response = make_response(jsonify({
            "message": "Login successful",
            "user": user_data,
        }), 200)
        set_access_cookies(response, access_token)
        logger.info(f"Login successful for {username}. Access cookie set.")
        return response
    else:
        logger.warning(f"Login failed for username: {username}. Invalid credentials.")
        return jsonify({"detail": "Invalid credentials"}), 401

@app.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    response = make_response(jsonify({"message": "Successfully logged out"}), 200)
    unset_jwt_cookies(response)
    logger.info(f"User {get_jwt_identity()} logged out. Access cookie unset.")
    return response

@app.route("/verify_auth", methods=["GET"])
@jwt_required(optional=True)
def verify_auth():
    db: Session = next(get_db())
    current_username = get_jwt_identity()
    if current_username:
        user = db.query(User).filter(User.username == current_username).first()
        if user:
            user_data = {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "email": user.email,
                "department": user.department,
                "role": get_frontend_role(user.role),
                "is_active": getattr(user, "is_active", True)
            }
            logger.info(f"Verify Auth: User {current_username} authenticated.")
            return jsonify({
                "isAuthenticated": True,
                "message": "Authenticated",
                "user": user_data
            }), 200
        else:
            logger.warning(f"Verify Auth: User {current_username} from token not found in DB.")
            return jsonify({
                "isAuthenticated": False,
                "message": "User associated with token not found"
            }), 401
    else:
        logger.info("Verify Auth: No valid token or token expired/invalid. Not authenticated.")
        return jsonify({
            "isAuthenticated": False,
            "message": "Not authenticated or session expired"
        }), 401

@app.route("/request_password_reset", methods=["POST"])
def request_password_reset():
    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"detail": "Email is required"}), 400

    db: Session = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    db.close()

    if not user:
        print(f"Password reset requested for non-existent email: {email}")
        return jsonify({"message": "If an account with that email exists, a password reset link has been sent."}), 200

    reset_token = secrets.token_urlsafe(32)
    print(f"\n--- Password Reset Link for {user.username} ({user.email}) ---")
    print(f"Reset Link: http://localhost:8081/reset_password?token={reset_token}")
    print("-----------------------------------------------------\n")

    return jsonify({"message": "If an account with that email exists, a password reset link has been sent."}), 200

# --- Register Blueprints ---
app.register_blueprint(user_bp)
app.register_blueprint(permission_bp)
app.register_blueprint(survey_bp)

if __name__ == "__main__":
    logger.info("Flask app running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000, host="0.0.0.0")