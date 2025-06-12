# F:\LLS Survey\backend\routes\permission_routes.py
from flask import Blueprint, request, jsonify
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Department, Permission, User # Import User model
from security import get_frontend_role # Ensure this is imported for user role normalization
from sqlalchemy.exc import IntegrityError
from datetime import datetime # For date parsing
from flask_jwt_extended import jwt_required, get_jwt_identity # Import JWT decorators

permission_bp = Blueprint('permission_bp', __name__, url_prefix='/api')

# Helper function to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# GET all departments (for admin matrix headers/rows)
@permission_bp.route('/departments', methods=['GET'])
@jwt_required() # Protect this endpoint
def get_departments():
    db: Session = next(get_db())
    departments = db.query(Department).order_by(Department.name).all() # Order by name for consistent display
    
    departments_data = [{"id": dept.id, "name": dept.name} for dept in departments]
    return jsonify(departments_data), 200

# POST (Create) a new department (likely used elsewhere, but kept here)
@permission_bp.route('/departments', methods=['POST'])
@jwt_required()
def create_department():
    data = request.get_json()
    dept_name = data.get('name')

    if not dept_name:
        return jsonify({"message": "Department name is required"}), 400

    db: Session = next(get_db())
    try:
        existing_dept = db.query(Department).filter(Department.name.ilike(dept_name)).first() # Case-insensitive check
        if existing_dept:
            return jsonify({"message": f"Department '{dept_name}' already exists"}), 409 # Conflict

        new_dept = Department(name=dept_name)
        db.add(new_dept)
        db.commit()
        db.refresh(new_dept)
        return jsonify({"id": new_dept.id, "name": new_dept.name}), 201
    except IntegrityError: # Catch specific SQLAlchemy integrity errors
        db.rollback()
        return jsonify({"message": "Database integrity error. Department might already exist (duplicate)."}), 409
    except Exception as e:
        db.rollback()
        print(f"Error creating department: {e}")
        return jsonify({"message": f"Internal server error: {str(e)}"}), 500
    finally:
        db.close()

# GET existing permissions (for populating the admin matrix on load)
@permission_bp.route('/permissions', methods=['GET'])
@jwt_required()
def get_permissions():
    db: Session = next(get_db())
    permissions = db.query(Permission).all()
    
    permissions_data = []
    for perm in permissions:
        permissions_data.append({
            "id": perm.id, # Include ID if needed for frontend keying
            "from_department_id": perm.from_department_id,
            "to_department_id": perm.to_department_id,
            "can_survey_self": perm.can_survey_self, # Return can_survey_self
            "start_date": perm.start_date.isoformat() if perm.start_date else None,
            "end_date": perm.end_date.isoformat() if perm.end_date else None,
        })
    return jsonify(permissions_data), 200

# POST to save permissions (replace all existing with new list)
# This endpoint now handles the full state of the matrix, including dates and self-survey.
@permission_bp.route('/permissions', methods=['POST']) # Route changed from /permissions/save
@jwt_required()
def set_permissions():
    data = request.get_json()
    allowed_pairs = data.get('allowed_pairs', []) # list of {"from_dept_id": int, "to_dept_id": int, "can_survey_self": bool}
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')

    if not isinstance(allowed_pairs, list):
        return jsonify({"message": "Invalid data format. 'allowed_pairs' must be a list."}), 400
    if not start_date_str or not end_date_str:
        return jsonify({"message": "Start date and end date are required."}), 400

    try:
        # datetime.fromisoformat handles 'Z' (Zulu time) correctly since Python 3.11,
        # otherwise, .replace('Z', '+00:00') is safer for older versions.
        start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({"message": "Invalid date format. Expected ISO string (e.g., YYYY-MM-DDTHH:MM:SS.sssZ)."}), 400

    db: Session = next(get_db())
    try:
        # Clear existing permissions for simplicity (as your frontend sends full matrix)
        db.query(Permission).delete()
        db.commit()
        print("Existing permissions wiped from DB.")

        new_permission_objects = []
        for pair in allowed_pairs:
            from_dept_id = pair.get('from_dept_id')
            to_dept_id = pair.get('to_dept_id')
            can_survey_self = pair.get('can_survey_self', False) # Default to False if not provided

            if from_dept_id is None or to_dept_id is None:
                print(f"Skipping permission: Invalid pair format - from_dept_id or to_dept_id missing. Pair: {pair}")
                continue # Skip invalid pair

            # Basic validation: ensure department IDs actually exist
            from_dept_exists = db.query(Department).filter_by(id=from_dept_id).first()
            to_dept_exists = db.query(Department).filter_by(id=to_dept_id).first()

            if not from_dept_exists or not to_dept_exists:
                print(f"Skipping permission: Department not found. From ID: {from_dept_id}, To ID: {to_dept_id}. Pair: {pair}")
                continue

            # If it's a self-survey, only allow if can_survey_self is explicitly True
            if from_dept_id == to_dept_id and not can_survey_self:
                print(f"Skipping self-survey for department {from_dept_id} as can_survey_self is false.")
                continue

            new_permission_objects.append(
                Permission(
                    from_department_id=from_dept_id,
                    to_department_id=to_dept_id,
                    start_date=start_date,
                    end_date=end_date,
                    can_survey_self=can_survey_self # Save the self-survey flag
                )
            )
        
        db.add_all(new_permission_objects)
        db.commit()
        print(f"Saved {len(new_permission_objects)} new permission entries.")
        return jsonify({"message": "Permissions saved successfully"}), 200

    except IntegrityError as e:
        db.rollback()
        print(f"Integrity error during permission setting: {e}")
        return jsonify({"message": f"Database error: {str(e)}"}), 500
    except Exception as e:
        db.rollback()
        print(f"Error setting permissions: {e}")
        return jsonify({"message": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        db.close()


# POST for Mail Alert Users
@permission_bp.route('/permissions/mail-alert', methods=['POST'])
@jwt_required()
def mail_alert_users():
    data = request.get_json()
    allowed_pairs = data.get('allowed_pairs', []) # This payload is only for identifying which users to alert
    start_date_str = data.get('start_date')
    end_date_str = data.get('end_date')

    if not allowed_pairs or not start_date_str or not end_date_str:
        return jsonify({"message": "Missing allowed_pairs or date range for mail alert"}), 400

    try:
        start_date = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
        end_date = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
    except ValueError:
        return jsonify({"message": "Invalid date format. Expected ISO string."}), 400

    db: Session = next(get_db())
    
    # Get department names for logging and user lookup
    department_names_map = {dept.id: dept.name for dept in db.query(Department).all()}

    # Identify unique "from" department IDs that are actually involved in permissions
    from_dept_ids = {pair['from_dept_id'] for pair in allowed_pairs if 'from_dept_id' in pair}
    
    users_to_alert = []
    # Find users belonging to these 'from' departments
    for dept_id in from_dept_ids:
        dept_name = department_names_map.get(dept_id)
        if dept_name:
            users_in_dept = db.query(User).filter(User.department == dept_name).all()
            users_to_alert.extend(users_in_dept)

    alert_summary = []
    if not users_to_alert:
        print("No users found in the relevant departments for mail alert.")
        return jsonify({"message": "Mail alert process initiated. No relevant users found for simulation."}), 200

    # Compile surveyable departments for each user based on the *provided* allowed_pairs
    for user in users_to_alert:
        # Filter allowed_pairs relevant to this user's department
        user_dept_id = next((d_id for d_id, d_name in department_names_map.items() if d_name == user.department), None)
        
        if user_dept_id is None:
            continue # Should not happen if user.department is valid

        relevant_permissions_for_user = [
            pair for pair in allowed_pairs 
            if pair['from_dept_id'] == user_dept_id
        ]
        
        # Filter out self-survey if can_survey_self is false for that specific permission
        surveyable_depts_names = []
        for p in relevant_permissions_for_user:
            # Need to get the actual permission from the DB to check can_survey_self
            # or ensure frontend sends can_survey_self in the allowed_pairs for this alert
            # For simplicity, assuming allowed_pairs already filtered self-survey or handles it.
            # However, the backend should ideally check its own DB state if can_survey_self is critical here.
            # For this 'mail-alert' endpoint, we rely on `allowed_pairs` provided by frontend.
            
            # If the original frontend matrix code filters out self-ratings where can_survey_self=false,
            # then we just need to map the to_dept_id to name.
            # If the `allowed_pairs` from frontend *includes* self-ratings where can_survey_self=false,
            # then we'd need to filter them out here.
            
            # Given that `ManagePermissions.tsx` (your frontend) does `fromId !== toId` when building `allowedPairs` for `handleSaveChanges`
            # and when building `currentAllowedPairs` for `handleMailAlert`, we can assume self-surveys where not allowed are already filtered.
            
            to_dept_name = department_names_map.get(p['to_dept_id'])
            if to_dept_name: # and (p['from_dept_id'] != p['to_dept_id'] or p.get('can_survey_self', False)): # More robust check if frontend sends can_survey_self
                surveyable_depts_names.append(to_dept_name)

        if surveyable_depts_names:
            alert_summary.append(
                f"Simulating email to user '{user.username}' ({user.email}) from department '{user.department}'. "
                f"Can now survey: {', '.join(surveyable_depts_names)}. Survey period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}."
            )
            print(alert_summary[-1]) # Print to backend console

    return jsonify({
        "message": "Mail alert process initiated (simulated). Check backend logs for details.",
        "alert_details": alert_summary
    }), 200

# NEW ENDPOINT: Get departments that the logged-in user's department can survey (for User Frontend)
@permission_bp.route('/surveyable-departments', methods=['GET'])
@jwt_required()
def get_surveyable_departments():
    db: Session = next(get_db())
    current_username = get_jwt_identity()
    
    try:
        current_user = db.query(User).filter(User.username == current_username).first()
        if not current_user:
            return jsonify({"detail": "User not found."}), 404
        
        # Get the ID of the logged-in user's department
        from_department_obj = db.query(Department).filter(Department.name == current_user.department).first()
        if not from_department_obj:
            # If user's department name doesn't exist in DB, they can't survey anything
            return jsonify({"detail": f"Department '{current_user.department}' not found or registered."}), 404
        
        from_department_id = from_department_obj.id
        current_date = datetime.utcnow()

        # Query permissions to find which departments the user's department can survey
        surveyable_permissions = db.query(Permission).filter(
            Permission.from_department_id == from_department_id,
            Permission.start_date <= current_date,
            Permission.end_date >= current_date # Ensure permission is active
        ).all()

        surveyable_departments_data = []
        for perm in surveyable_permissions:
            to_dept = db.query(Department).filter_by(id=perm.to_department_id).first()
            if to_dept:
                # IMPORTANT: Only include if self-survey is allowed, OR if it's not a self-survey
                if perm.from_department_id == perm.to_department_id and not perm.can_survey_self:
                    continue # Skip if it's a self-survey and not allowed by permission rule
                
                surveyable_departments_data.append({
                    "id": to_dept.id,
                    "name": to_dept.name
                })
        
        # Sort for consistent display in frontend
        surveyable_departments_data.sort(key=lambda x: x['name'])

        if not surveyable_departments_data:
            return jsonify({"message": "No departments are currently available for you to survey."}), 200

        return jsonify(surveyable_departments_data), 200

    except Exception as e:
        print(f"Error fetching surveyable departments: {e}")
        return jsonify({"detail": f"An error occurred fetching surveyable departments: {str(e)}"}), 500
    finally:
        db.close()
