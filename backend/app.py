# F:\LLS Survey\backend\app.py
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file

from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from sqlalchemy.orm import Session
from flask_jwt_extended import create_access_token, JWTManager, jwt_required, get_jwt_identity, unset_jwt_cookies, set_access_cookies
from datetime import timedelta
import os
import secrets
import logging

# Configure logging to show info messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import custom modules
from security import verify_password, get_frontend_role, hash_password # hash_password added for initial user creation if needed
from database import SessionLocal, engine, Base # Import Base and engine to potentially create tables here or in a script
from models import User, Department # Import models needed directly in app.py

# Import blueprints for modular routing
from routes.user_routes import user_bp
from routes.permission_routes import permission_bp
from routes.survey_routes import survey_bp

app = Flask(__name__)

# --- Flask Configuration ---
app.secret_key = os.getenv("FLASK_SECRET_KEY", "another_super_secret_key_for_flask_CHANGE_THIS")

# --- Flask-JWT-Extended Configuration ---
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "your_super_secret_jwt_key_CHANGE_THIS_IN_PRODUCTION")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1) # Token expires after 1 hour
app.config["JWT_TOKEN_LOCATION"] = ["cookies"] # Store JWT in cookies
app.config["JWT_COOKIE_SECURE"] = False # Set to True in production for HTTPS
app.config["JWT_COOKIE_CSRF_PROTECT"] = False # Set to True in production with proper CSRF handling
app.config["JWT_ACCESS_TOKEN_NAME"] = 'access_token_cookie' # Name of the access token cookie
# For local development, set to 'localhost' or your frontend's domain/IP
app.config["JWT_COOKIE_DOMAIN"] = 'localhost'
app.config["JWT_COOKIE_PATH"] = '/' # Cookie valid for all paths

jwt = JWTManager(app)
# --- END JWT Configuration ---

# Debugging JWT config (useful to see if env vars are loaded)
print(f"DEBUG: app.config['JWT_SECRET_KEY'] is set to: {'***KEY_IS_SET***' if app.config['JWT_SECRET_KEY'] else '!!!KEY_IS_NOT_SET!!!'}")
print(f"DEBUG: JWT_COOKIE_CSRF_PROTECT is: {app.config['JWT_COOKIE_CSRF_PROTECT']}")
print(f"DEBUG: JWT_ACCESS_TOKEN_NAME is: {app.config['JWT_ACCESS_TOKEN_NAME']}")
print(f"DEBUG: JWT_COOKIE_DOMAIN is: {app.config['JWT_COOKIE_DOMAIN']}")
print(f"DEBUG: JWT_COOKIE_PATH is: {app.config['JWT_COOKIE_PATH']}")

# --- CORS Configuration ---
# Allow requests from your frontend development servers and allow credentials (cookies)
CORS(app, resources={r"/*": {"origins": ["http://localhost:8080", "http://localhost:8081", "http://localhost:5173"]}}, supports_credentials=True)

# Helper function to get a database session for a request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Core Authentication Routes (not part of a blueprint, directly on app) ---

@app.route("/login", methods=["POST"])
def login():
    db: Session = next(get_db())
    username = request.json.get("username", None)
    password = request.json.get("password", None)

    logger.info(f"Login attempt for username: {username}") 

    user = db.query(User).filter(User.username == username).first()

    if user and verify_password(password, user.hashed_password):
        # Prepare user data to send to frontend (excluding hashed password)
        user_data = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "department": user.department, # This is the department NAME
            "role": get_frontend_role(user.role),
            "is_active": user.is_active
        }

        # Create access token for the authenticated user
        access_token = create_access_token(identity=user.username) # Using username as identity

        response = make_response(jsonify({
            "message": "Login successful",
            "user": user_data,
        }), 200)
        
        # Set the JWT access token as an HttpOnly cookie
        set_access_cookies(response, access_token)
        logger.info(f"Login successful for {username}. Access cookie set.")
        return response
    else:
        logger.warning(f"Login failed for username: {username}. Invalid credentials.")
        return jsonify({"detail": "Invalid username or password"}), 401

@app.route("/logout", methods=["POST"])
@jwt_required() # Requires a valid JWT to logout (protects against casual logout)
def logout():
    response = make_response(jsonify({"message": "Successfully logged out"}), 200)
    # Remove the JWT cookie
    unset_jwt_cookies(response)
    logger.info(f"User {get_jwt_identity()} logged out. Access cookie unset.")
    return response

@app.route("/verify_auth", methods=["GET"])
@jwt_required(optional=True) # Allows endpoint to be accessed without a token, returns None for identity
def verify_auth():
    db: Session = next(get_db())
    current_username = get_jwt_identity() # This will be None if no valid token is present or token is expired

    if current_username:
        user = db.query(User).filter(User.username == current_username).first()
        if user:
            # Return full user data to sync frontend state
            user_data = {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "email": user.email,
                "department": user.department,
                "role": get_frontend_role(user.role),
                "is_active": user.is_active
            }
            logger.info(f"Verify Auth: User {current_username} authenticated and user data retrieved.")
            return jsonify({
                "isAuthenticated": True,
                "message": "Authenticated",
                "user": user_data
            }), 200
        else:
            logger.warning(f"Verify Auth: Token provided for user {current_username}, but user not found in DB.")
            # If user from token is not in DB, effectively not authenticated
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

# --- Password Reset Request (for testing/development purposes, not production-ready without email service) ---
@app.route("/request_password_reset", methods=["POST"])
def request_password_reset():
    data = request.get_json()
    email = data.get("email")

    if not email:
        return jsonify({"detail": "Email is required"}), 400

    db: Session = next(get_db())
    user = db.query(User).filter(User.email == email).first()
    db.close()

    if not user:
        # Avoid giving away if email exists. Send generic success message.
        print(f"Password reset requested for non-existent email: {email}. (Simulated)")
        return jsonify({"message": "If an account with that email exists, a password reset link has been sent."}), 200

    # In a real application, you would generate a secure token, store it with an expiry,
    # and send an email to the user with a link to reset their password.
    reset_token = secrets.token_urlsafe(32) 
    print(f"\n--- SIMULATED Password Reset Link for {user.username} ({user.email}) ---")
    print(f"Reset Link: http://localhost:8081/reset_password?token={reset_token}") # Frontend reset page URL
    print("-------------------------------------------------------------------\n")

    return jsonify({"message": "If an account with that email exists, a password reset link has been sent."}), 200


# --- Register Blueprints ---
# Each blueprint handles a specific set of related routes (e.g., users, permissions, surveys)
app.register_blueprint(user_bp)
app.register_blueprint(permission_bp)
app.register_blueprint(survey_bp)

# --- Basic Home Route ---
@app.route('/')
def home():
    """Basic home route to confirm API is running."""
    return "Survey Backend API is running!"

# --- Application Entry Point ---
if __name__ == '__main__':
    # You might want to run create_tables() here on initial setup if your DB isn't pre-created
    # from models import create_tables
    # with app.app_context(): # Run within app context if using Flask-specific features
    #     create_tables()

    logger.info(f"Flask app running on http://127.0.0.1:5000")
    # Run the Flask development server
    # host='0.0.0.0' makes the server accessible from other machines on the network
    # (e.g., if you're testing from another device or within a Docker container).
    # For typical local development, '127.0.0.1' or no host argument (defaulting to localhost) is fine.
    app.run(debug=True, port=5000, host='0.0.0.0')
