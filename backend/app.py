# F:\LLS Survey\backend\app.py
from dotenv import load_dotenv
load_dotenv() # Ensure this is at the very top, before other imports that might depend on env vars

from flask import Flask, request, jsonify, make_response, url_for
from flask_cors import CORS
from sqlalchemy.orm import Session
from flask_jwt_extended import create_access_token, JWTManager, jwt_required, get_jwt_identity, unset_jwt_cookies, set_access_cookies
from datetime import timedelta
import os
import secrets

from security import verify_password, get_frontend_role, hash_password
from database import SessionLocal
from models import User, Department
from routes.user_routes import user_bp
from routes.permission_routes import permission_bp
from routes.survey_routes import survey_bp


app = Flask(__name__)

# --- Flask's Native SECRET_KEY (Good practice to set this too) ---
app.secret_key = os.getenv("FLASK_SECRET_KEY", "another_super_secret_key_for_flask_CHANGE_THIS")

# --- Flask-JWT-Extended Configuration ---
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "your_super_secret_jwt_key_CHANGE_THIS_IN_PRODUCTION")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_COOKIE_SECURE"] = False # Set to True in production for HTTPS
app.config["JWT_COOKIE_CSRF_PROTECT"] = True # Enable CSRF protection for cookies
jwt = JWTManager(app)
# --- END JWT Configuration ---

# DIAGNOSTIC PRINT: Check what JWT_SECRET_KEY is being used
print(f"DEBUG: app.config['JWT_SECRET_KEY'] is set to: {'***KEY_IS_SET***' if app.config['JWT_SECRET_KEY'] else '!!!KEY_IS_NOT_SET!!!'}")


# Configure CORS - CRUCIAL for your two frontends to exchange cookies
CORS(app, resources={r"/*": {"origins": ["http://localhost:8080", "http://localhost:8081", "http://localhost:5173"]}}, supports_credentials=True)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- User Authentication Routes ---
@app.route("/login", methods=["POST"])
def login():
    db: Session = next(get_db())
    username = request.json.get("username", None)
    password = request.json.get("password", None)

    user = db.query(User).filter(User.username == username).first()

    if user and verify_password(password, user.hashed_password):
        # Create user data dictionary to return, normalizing role
        user_data = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "department": user.department, # This is the department name (string)
            "role": get_frontend_role(user.role), # Normalized role for frontend
            "is_active": user.is_active
        }

        # Create the access token
        access_token = create_access_token(identity=user.username)
        
        # Set the JWT cookie in the response
        response = make_response(jsonify({
            "message": "Login successful",
            "user": user_data, # Return the full user object
        }), 200)
        set_access_cookies(response, access_token)
        return response
    else:
        return jsonify({"detail": "Invalid credentials"}), 401

@app.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    response = make_response(jsonify({"message": "Successfully logged out"}), 200)
    unset_jwt_cookies(response)
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
                "is_active": user.is_active
            }
            return jsonify({
                "isAuthenticated": True,
                "message": "Authenticated",
                "user": user_data
            }), 200
        else:
            return jsonify({
                "isAuthenticated": False,
                "message": "User associated with token not found"
            }), 401
    else:
        return jsonify({
            "isAuthenticated": False,
            "message": "Not authenticated or session expired"
        }), 401

# --- Password Reset (for testing purposes, not for production without email service) ---
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

# --- Application Entry Point ---
if __name__ == '__main__':
    print(f"Flask app running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000, host='0.0.0.0')

