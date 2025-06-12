# routes/user_routes.py
from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from database import SessionLocal
from models import User
from security import hash_password, verify_password

user_bp = Blueprint('user_bp', __name__, url_prefix='/api')

# Helper function to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper function to normalize role for frontend consumption
def get_frontend_role(db_role: str) -> str:
    """Normalizes the database role to 'admin' or 'user' for frontend."""
    if db_role.lower() == 'admin':
        return 'admin'
    return 'user' # Any other role (Rep, Manager, etc.) is considered 'user' for frontend

# GET all users
@user_bp.route('/users', methods=['GET'])
def get_users():
    db: Session = next(get_db())
    users = db.query(User).all()

    users_data = []
    for user in users:
        users_data.append({
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "email": user.email,
            "department": user.department,
            "role": get_frontend_role(user.role), # Normalize role for frontend
            "status": "Submitted" if user.created_at else "Not Submitted"
        })
    return jsonify(users_data)

# POST (Create) a new user
@user_bp.route('/users', methods=['POST'])
def create_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    name = data.get('name')
    email = data.get('email')
    department = data.get('department')
    role = data.get('role', 'Rep') # Default role to 'Rep' if not provided by frontend

    if not all([username, password, name, email, department]):
        return jsonify({"message": "Missing required fields"}), 400

    db: Session = next(get_db())

    if db.query(User).filter((User.username == username) | (User.email == email)).first():
        return jsonify({"message": "User with this username or email already exists"}), 409

    hashed_password = hash_password(password)

    new_user = User(
        username=username,
        name=name,
        email=email,
        department=department,
        hashed_password=hashed_password,
        role=role # Store the specific role (Rep, Manager, Admin) in the DB
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return jsonify({
        "id": new_user.id,
        "username": new_user.username,
        "name": new_user.name,
        "email": new_user.email,
        "department": new_user.department,
        "role": get_frontend_role(new_user.role), # Normalize role for frontend in response
        "status": "Not Submitted"
    }), 201

# PUT (Update) an existing user
@user_bp.route('/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    data = request.get_json()
    db: Session = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        return jsonify({"message": "User not found"}), 404

    if 'name' in data:
        user.name = data['name']
    if 'email' in data:
        user.email = data['email']
    if 'department' in data:
        user.department = data['department']
    if 'role' in data:
        user.role = data['role'] # Update the specific role in the DB

    db.commit()
    db.refresh(user)

    return jsonify({
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "email": user.email,
        "department": user.department,
        "role": get_frontend_role(user.role), # Normalize role for frontend in response
        "status": "Submitted" if user.created_at else "Not Submitted"
    })

# DELETE a user
@user_bp.route('/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    db: Session = next(get_db())
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        return jsonify({"message": "User not found"}), 404

    db.delete(user)
    db.commit()

    return jsonify({"message": "User deleted successfully"}), 200
