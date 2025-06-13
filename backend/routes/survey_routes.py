# F:\LLS Survey\backend\routes\survey_routes.py
from flask import Blueprint, request, jsonify, abort, send_file
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, cast, String
from database import SessionLocal
# Corrected import line - Removed 'Response' as it's no longer used/defined in current models
from models import Survey, Question, Option, Answer, User, Department, RemarkResponse, SurveySubmission 
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError, NoResultFound
from datetime import datetime, timedelta
import pandas as pd
import io

survey_bp = Blueprint('survey', __name__, url_prefix='/api')

# Helper function to determine rating description based on percentage
def get_rating_description(overall_rating: float) -> str:
    if overall_rating >= 91:
        return "Excellent - Exceeds the Customer Expectation"
    elif overall_rating >= 75:
        return "Satisfactory - Meets the Customer requirement"
    elif overall_rating >= 70:
        return "Below Average - Identify areas for improvement and initiate action to eliminate dissatisfaction"
    else:
        return "Poor - Identify areas for improvement and initiate action to eliminate dissatisfaction"

# Helper function for filtering submissions by time period for exports/summaries
def filter_submissions_by_time_period_sql(db: Session, time_period: str, base_query):
    """
    Applies date filtering to a base SQLAlchemy query.
    `base_query` should typically be a query on the `SurveySubmission` model.
    """
    query = base_query
    current_date = datetime.utcnow()

    if time_period == "last_7_days":
        start_date = current_date - timedelta(days=7)
        query = query.filter(SurveySubmission.submitted_at >= start_date)
    elif time_period == "last_30_days":
        start_date = current_date - timedelta(days=30)
        query = query.filter(SurveySubmission.submitted_at >= start_date)
    elif time_period == "last_3_months":
        start_date = current_date - timedelta(days=90)
        query = query.filter(SurveySubmission.submitted_at >= start_date)
    elif time_period == "last_6_months":
        start_date = current_date - timedelta(days=180)
        query = query.filter(SurveySubmission.submitted_at >= start_date)
    elif time_period == "last_year":
        start_date = current_date - timedelta(days=365)
        query = query.filter(SurveySubmission.submitted_at >= start_date)
    elif time_period == 'all_time' or not time_period:
        pass # No date filter needed
    else:
        print(f"Warning: Invalid time period '{time_period}' received for filtering.")
        # Return an empty query if time_period is invalid or no filter needed
        return base_query.filter(False) if time_period else base_query

    return query


# Helper function to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --- Survey Management (CRUD for Surveys/Questions, typically Admin-side) ---

# Endpoint to create a new survey (Admin)
@survey_bp.route('/surveys', methods=['POST'])
@jwt_required() # Protect this endpoint if only admins can create surveys
def create_survey():
    db: Session = next(get_db())
    data = request.get_json()

    if not all([key in data for key in ['title', 'description', 'managing_department_id', 'rated_department_id', 'questions']]):
        return jsonify({"detail": "Missing required survey fields"}), 400

    try:
        new_survey = Survey(
            title=data['title'],
            description=data.get('description'),
            managing_department_id=data['managing_department_id'],
            rated_department_id=data['rated_department_id']
        )
        db.add(new_survey)
        db.commit()
        db.refresh(new_survey)

        for q_data in data['questions']:
            new_question = Question(
                survey_id=new_survey.id,
                category=q_data.get('category'),
                text=q_data['text'],
                type=q_data.get('type', 'rating'),
                order=q_data.get('order', 0)
            )
            db.add(new_question)
            db.commit()
            db.refresh(new_question)

            if new_question.type == 'multiple_choice' and 'options' in q_data:
                for opt_data in q_data['options']:
                    new_option = Option(
                        question_id=new_question.id,
                        text=opt_data['text'],
                        value=opt_data.get('value')
                    )
                    db.add(new_option)
        db.commit()

        return jsonify({"message": "Survey created successfully", "survey_id": new_survey.id}), 201
    except IntegrityError as e:
        db.rollback()
        print(f"Database integrity error creating survey: {e}")
        return jsonify({"detail": "Error creating survey due to existing data or foreign key issue."}), 500
    except Exception as e:
        db.rollback()
        print(f"Error creating survey: {e}")
        return jsonify({"detail": f"An unexpected error occurred: {str(e)}"}), 500
    finally:
        db.close()

# Endpoint to fetch a specific survey by ID (for display or editing)
@survey_bp.route('/surveys/<int:survey_id>', methods=['GET'])
# @jwt_required() # <-- Keep this commented out for now for easier frontend development
def get_survey_template_by_id(survey_id: int):
    db: Session = next(get_db())
    survey = db.query(Survey).options(
        joinedload(Survey.questions).joinedload(Question.options),
        joinedload(Survey.managing_department), # Eager load related departments
        joinedload(Survey.rated_department)
    ).filter(Survey.id == survey_id).first()

    if not survey:
        abort(404, description="Survey not found")

    survey_data = {
        "id": survey.id,
        "title": survey.title,
        "description": survey.description,
        "created_at": survey.created_at.isoformat() if survey.created_at else None,
        "managing_department_id": survey.managing_department_id,
        "rated_department_id": survey.rated_department_id,
        "managing_dept_name": survey.managing_department.name if survey.managing_department else "N/A",
        "rated_dept_name": survey.rated_department.name if survey.rated_department else "N/A",
        "questions": []
    }

    questions_data = []
    for question in survey.questions:
        q_data = {
            "id": question.id,
            "text": question.text,
            "type": question.type,
            "order": question.order,
            "category": question.category,
            "options": []
        }
        if question.type == 'multiple_choice':
            for option in question.options:
                q_data['options'].append({
                    "id": option.id,
                    "text": option.text,
                    "value": option.value
                })
        questions_data.append(q_data)
    
    # Sort questions by order for consistent display
    survey_data['questions'] = sorted(questions_data, key=lambda q: q['order'])

    return jsonify(survey_data), 200

# Endpoint to get all survey templates (for general overview, e.g., in admin list of surveys)
@survey_bp.route('/surveys', methods=['GET'])
@jwt_required()
def get_all_surveys():
    db = SessionLocal()
    try:
        surveys = db.query(Survey).all()
        result = []
        for s in surveys:
            result.append({
                "id": s.id,
                "title": s.title,
                "description": s.description,
                "created_at": str(s.created_at),
                "rated_dept_name": s.rated_department.name,
                "managing_dept_name": s.managing_department.name,
                "rated_department_id": s.rated_department_id,
                "managing_department_id": s.managing_department_id,
                "questions": [
                    {
                        "id": q.id,
                        "text": q.text,
                        "type": q.type,
                        "order": q.order,
                        "category": q.category,
                        "options": [
                            {"id": o.id, "text": o.text, "value": o.value} for o in q.options
                        ] if q.options else []
                    } for q in s.questions
                ]
            })
        return jsonify(result), 200
    except Exception as e:
        print(f"Error fetching surveys: {e}")
        return jsonify({"detail": "Failed to fetch surveys."}), 500
    finally:
        db.close()


# Endpoint to submit a survey response (from SurveyForm.tsx)
@survey_bp.route('/submit-survey', methods=['POST'])
@jwt_required() # User must be logged in to submit
def submit_survey_response():
    db: Session = next(get_db())
    data = request.get_json()

    current_username = get_jwt_identity()
    submitter_user = db.query(User).filter(User.username == current_username).first()

    if not submitter_user:
        return jsonify({"detail": "Authenticated user not found in database."}), 404

    # Validate incoming payload structure
    required_fields = [
        'survey_id', 'department_id', 'submitter_department_id',
        'questions_data', 'summary_metrics'
    ]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field in payload: {field}"}), 400

    survey_template_id = data['survey_id']
    rated_department_id = data['department_id']
    submitter_department_id = data['submitter_department_id']
    questions_data = data['questions_data']
    summary_metrics = data['summary_metrics']
    final_suggestion = summary_metrics.get('suggestions')

    # Basic validation of summary_metrics
    if not isinstance(summary_metrics.get('overall_customer_rating'), (int, float)):
        return jsonify({"error": "summary_metrics.overall_customer_rating is required and must be a number."}), 400

    try:
        # Verify survey template exists
        survey_template = db.query(Survey).filter(
            Survey.id == survey_template_id,
            Survey.rated_department_id == rated_department_id
        ).first()
        if not survey_template:
            return jsonify({"detail": "Survey template not found for the specified rated department."}), 404

        # Check for duplicate submission by this user for this survey template
        existing_submission = db.query(SurveySubmission).filter(
            SurveySubmission.survey_id == survey_template_id,
            SurveySubmission.submitter_user_id == submitter_user.id
        ).first()
        if existing_submission:
            return jsonify({"detail": "You have already submitted this survey."}), 409

        # Create new SurveySubmission
        new_submission = SurveySubmission(
            survey_id=survey_template_id,
            submitter_user_id=submitter_user.id,
            submitter_department_id=submitter_department_id,
            rated_department_id=rated_department_id,
            submitted_at=datetime.utcnow(),
            overall_customer_rating=summary_metrics['overall_customer_rating'],
            rating_description=summary_metrics.get('rating_description'),
            suggestions=final_suggestion,
        )
        db.add(new_submission)
        db.flush() # Flush to get new_submission.id before processing answers

        # Process individual answers
        for ans_data in questions_data:
            question_id = ans_data.get('id')
            
            # Verify question exists and belongs to the survey template
            question_obj = db.query(Question).filter(
                Question.id == question_id,
                Question.survey_id == survey_template_id
            ).first()
            
            if not question_obj:
                print(f"Warning: Question ID {question_id} not found for survey {survey_template_id}. Skipping answer.")
                continue

            new_answer = Answer(
                submission_id=new_submission.id,
                question_id=question_id,
                rating_value=ans_data.get('rating'),
                text_response=ans_data.get('remarks'),
                # selected_option_id=ans_data.get('selected_option_id') # Add if you have multiple choice questions
            )
            db.add(new_answer)
        
        db.commit()
        return jsonify({"message": "Survey submitted successfully", "submission_id": new_submission.id}), 201

    except IntegrityError as e:
        db.rollback()
        print(f"IntegrityError during survey submission: {e}")
        return jsonify({"detail": "Database integrity error. Possible duplicate submission or invalid data."}), 400
    except NoResultFound:
        db.rollback()
        return jsonify({"detail": "Required data (user/department/survey template) not found in database for submission."}), 400
    except Exception as e:
        db.rollback()
        print(f"Error submitting survey: {e}")
        return jsonify({"detail": f"An unexpected error occurred during submission: {str(e)}"}), 500
    finally:
        db.close()


# NEW ENDPOINT: Get surveys submitted by the current user (for DepartmentSelection.tsx)
@survey_bp.route('/user-submissions', methods=['GET'])
@jwt_required()
def get_user_submissions():
    db: Session = SessionLocal()
    try:
        current_username = get_jwt_identity()
        user = db.query(User).filter_by(username=current_username).first()

        if not user:
            return jsonify({"detail": "User not found"}), 404

        submissions = db.query(SurveySubmission).filter_by(submitter_user_id=user.id).all()

        result = []
        for s in submissions:
            result.append({
                "id": s.id,
                "survey_id": s.survey_id,
                "submitter_user_id": s.submitter_user_id,
                "submitter_department_id": s.submitter_department_id,
                "rated_department_id": s.rated_department_id,
                "submitted_at": str(s.submitted_at),
                "overall_customer_rating": s.overall_customer_rating,
                "suggestions": s.suggestions,
                "submitter_department_name": s.submitter_department.name,
                "rated_department_name": s.rated_department.name
            })

        return jsonify(result), 200
    except Exception as e:
        print(f"Error fetching user submissions: {e}")
        return jsonify({"detail": "Failed to fetch user submissions."}), 500
    finally:
        db.close()



# --- Remarks & Responses Management ---

@survey_bp.route('/remarks/incoming', methods=['GET'])
@jwt_required() # This must remain protected as it fetches user-specific data
def get_incoming_remarks():
    db: Session = SessionLocal()
    try:
        current_username = get_jwt_identity()
        current_user = db.query(User).filter(User.username == current_username).first()
        if not current_user or not current_user.department:
            return jsonify({"detail": "User or department not found"}), 404

        current_dept_obj = db.query(Department).filter_by(name=current_user.department).first()
        if not current_dept_obj:
            return jsonify({"detail": "User's department not registered in database"}), 404
        
        my_department_id = current_dept_obj.id

        incoming_remarks = []

        submissions = db.query(SurveySubmission).options(
            joinedload(SurveySubmission.answers).joinedload(Answer.question),
            joinedload(SurveySubmission.submitter_department),
            joinedload(SurveySubmission.rated_department)
        ).filter(
            SurveySubmission.rated_department_id == my_department_id
        ).all()

        for submission in submissions:
            for answer in submission.answers:
                if answer.text_response: # Only include answers with remarks
                    remark_response_exists = db.query(RemarkResponse).filter(
                        RemarkResponse.survey_submission_id == submission.id,
                        RemarkResponse.question_id == answer.question_id
                    ).first()

                    if not remark_response_exists: # Only include if no response exists
                        submission_date_str = submission.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if submission.submitted_at else None
                        
                        incoming_remarks.append({
                            "id": submission.id, # This is the SurveySubmission ID
                            "questionDataId": answer.question_id, # The Question ID this remark belongs to
                            "fromDepartment": submission.submitter_department.name if submission.submitter_department else 'Unknown',
                            "ratedDepartmentId": submission.rated_department_id,
                            "remark": answer.text_response,
                            "ratingGiven": answer.rating_value,
                            "surveyDate": submission_date_str,
                            "category": answer.question.category if answer.question else None,
                        })
    except Exception as e:
        print(f"Error fetching incoming remarks: {e}")
        return jsonify({"detail": f"Error fetching incoming remarks: {str(e)}"}), 500
    finally:
        db.close()
    
    return jsonify(incoming_remarks)


@survey_bp.route('/remarks/outgoing', methods=['GET'])
@jwt_required() # This must remain protected as it fetches user-specific data
def get_outgoing_remarks():
    db: Session = SessionLocal()
    try:
        current_username = get_jwt_identity()
        current_user = db.query(User).filter(User.username == current_username).first()
        if not current_user or not current_user.department:
            return jsonify({"detail": "User or department not found"}), 404

        current_dept_obj = db.query(Department).filter_by(name=current_user.department).first()
        if not current_dept_obj:
            return jsonify({"detail": "User's department not registered in database"}), 404
        
        my_department_id = current_dept_obj.id

        outgoing_remarks = []

        submissions = db.query(SurveySubmission).options(
            joinedload(SurveySubmission.answers).joinedload(Answer.question),
            joinedload(SurveySubmission.rated_department),
            joinedload(SurveySubmission.remark_responses) # Load remark responses directly
        ).filter(
            SurveySubmission.submitter_department_id == my_department_id
        ).all()

        for submission in submissions:
            rated_department_name = submission.rated_department.name if submission.rated_department else 'Unknown Department'
            submission_date_str = submission.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if submission.submitted_at else None

            for answer in submission.answers:
                if answer.text_response: # Only include answers with remarks
                    
                    # Find the associated remark response for this specific answer (question_id)
                    found_response = next(
                        (r for r in submission.remark_responses if r.question_id == answer.question_id),
                        None
                    )
                    
                    their_response = {
                        "explanation": found_response.explanation if found_response else "",
                        "actionPlan": found_response.action_plan if found_response else "",
                        "responsiblePerson": found_response.responsible_person if found_response else "",
                        "responseDate": found_response.responded_at.isoformat() if found_response and found_response.responded_at else ""
                    }
                    
                    outgoing_remarks.append({
                        "id": submission.id, # Survey Submission ID
                        "questionDataId": answer.question_id, # The Question ID
                        "department": rated_department_name, # Department that was rated (received remark)
                        "rating": answer.rating_value,
                        "yourRemark": answer.text_response,
                        "theirResponse": their_response,
                        "surveyDate": submission_date_str,
                        "category": answer.question.category if answer.question else None,
                    })
    except Exception as e:
        print(f"Error fetching outgoing remarks: {e}")
        return jsonify({"detail": f"Error fetching outgoing remarks: {str(e)}"}), 500
    finally:
        db.close()
    
    return jsonify(outgoing_remarks)


@survey_bp.route('/remarks/respond', methods=['POST'])
@jwt_required() # This must remain protected
def respond_to_remark():
    db: Session = SessionLocal()
    # The entire logic of the function should be within the try block
    try:
        current_username = get_jwt_identity()
        current_user = db.query(User).filter(User.username == current_username).first()

        if not current_user or not current_user.department:
            return jsonify({"detail": "User or department not found"}), 404

        responded_by_dept_obj = db.query(Department).filter_by(name=current_user.department).first()
        if not responded_by_dept_obj:
            return jsonify({"detail": "User's department not registered in database"}), 404
        
        responded_by_department_id = responded_by_dept_obj.id

        data = request.get_json()
        submission_id = data.get('survey_id') # This is the SurveySubmission.id
        question_id = data.get('question_data_id') # This is the Question.id
        explanation = data.get('explanation')
        action_plan = data.get('action_plan')
        responsible_person = data.get('responsible_person')

        if not all([submission_id, question_id, explanation, action_plan, responsible_person]):
            return jsonify({"detail": "Missing required fields"}), 400

        submission = db.query(SurveySubmission).filter(
            SurveySubmission.id == submission_id,
            SurveySubmission.rated_department_id == responded_by_department_id # Ensure this department is the one rated
        ).first()

        if not submission:
            return jsonify({"detail": "Submission not found or not authorized to respond for this department."}), 404

        # Check if a response already exists for this specific remark (submission + question)
        existing_remark_response = db.query(RemarkResponse).filter(
            RemarkResponse.survey_submission_id == submission_id,
            RemarkResponse.question_id == question_id
        ).first()

        if existing_remark_response:
            # Update existing response
            existing_remark_response.explanation = explanation
            existing_remark_response.action_plan = action_plan
            existing_remark_response.responsible_person = responsible_person
            existing_remark_response.responded_at = datetime.utcnow() # Update timestamp
            db.commit()
            return jsonify({"message": "Remark response updated successfully!"}), 200
        else:
            # Create a new remark response
            new_remark_response = RemarkResponse(
                survey_submission_id=submission_id,
                question_id=question_id,
                explanation=explanation,
                action_plan=action_plan,
                responsible_person=responsible_person,
                responded_by_department_id=responded_by_department_id,
                responded_at=datetime.utcnow()
            )
            db.add(new_remark_response)
            db.commit()
            return jsonify({"message": "Response submitted successfully!"}), 201

    except IntegrityError as e:
        db.rollback()
        print(f"IntegrityError during remark response submission: {e}")
        return jsonify({"detail": "Database integrity error. Possible duplicate response or invalid data."}), 400
    except Exception as e:
        db.rollback()
        print(f"Error submitting remark response: {e}")
        return jsonify({"detail": f"An unexpected error occurred during response submission: {str(e)}"}), 500
    finally:
        db.close()


# --- Dashboard Metrics ---

@survey_bp.route('/dashboard/overall-stats', methods=['GET'])
@jwt_required() # This must remain protected
def get_overall_dashboard_stats():
    db: Session = next(get_db())
    try:
        total_surveys_submitted = db.query(SurveySubmission).count()

        avg_overall_rating_query = db.query(func.avg(SurveySubmission.overall_customer_rating)).scalar()
        average_overall_rating = round(float(avg_overall_rating_query), 2) if avg_overall_rating_query else 0.0

        latest_submissions = db.query(SurveySubmission).options(
            joinedload(SurveySubmission.survey),
            joinedload(SurveySubmission.submitter)
        ).order_by(desc(SurveySubmission.submitted_at)).limit(5).all()

        latest_data = []
        for submission in latest_submissions:
            latest_data.append({
                "responseId": submission.id, # SurveySubmission ID
                "surveyTitle": submission.survey.title if submission.survey else 'N/A',
                "ratedDepartmentName": submission.rated_department.name if submission.rated_department else "N/A",
                "overallRating": float(submission.overall_customer_rating) if submission.overall_customer_rating is not None else 0.0,
                "submittedBy": submission.submitter.username if submission.submitter else "N/A", # Changed to username
                "submittedAt": submission.submitted_at.isoformat() if submission.submitted_at else "N/A"
            })

        return jsonify({
            "totalSurveysSubmitted": total_surveys_submitted,
            "averageOverallRating": average_overall_rating,
            "latestSubmissions": latest_data
        }), 200
    except Exception as e:
        print(f"Error fetching overall dashboard stats: {e}")
        return jsonify({"detail": f"Internal server error: {str(e)}"}), 500
    finally:
        db.close()

@survey_bp.route('/dashboard/department-metrics', methods=['GET'])
@jwt_required() # This must remain protected
def get_department_dashboard_metrics():
    db: Session = next(get_db())
    try:
        all_departments = db.query(Department).order_by(Department.name).all()
        all_departments_map = {dept.id: dept.name for dept in all_departments}
        
        rated_dept_metrics = db.query(
            SurveySubmission.rated_department_id,
            func.avg(SurveySubmission.overall_customer_rating).label('average_rating'),
            func.count(SurveySubmission.id).label('total_surveys')
        ).group_by(SurveySubmission.rated_department_id).all()

        metrics_by_id = {metric.rated_department_id: {"average_rating": metric.average_rating, "total_surveys": metric.total_surveys} for metric in rated_dept_metrics}

        final_department_metrics = []
        for dept in all_departments:
            metric_data = metrics_by_id.get(dept.id)
            if metric_data:
                final_department_metrics.append({
                    "department_id": dept.id,
                    "department_name": dept.name,
                    "average_rating": round(float(metric_data['average_rating']), 2),
                    "total_surveys": metric_data['total_surveys']
                })
            else:
                final_department_metrics.append({
                    "department_id": dept.id,
                    "department_name": dept.name,
                    "average_rating": 0.0,
                    "total_surveys": 0
                })
        
        final_department_metrics.sort(key=lambda x: x['department_name'])

        return jsonify(final_department_metrics), 200
    except Exception as e:
        print(f"Error fetching department dashboard metrics: {e}")
        return jsonify({"detail": f"Internal server error: {str(e)}"}), 500
    finally:
        db.close()


# --- Excel Export Routes ---

@survey_bp.route('/export-data', methods=['GET'])
@jwt_required()
def export_excel():
    db: Session = next(get_db())
    export_type = request.args.get('type')
    time_period = request.args.get('timePeriod')

    if not export_type:
        return jsonify({"error": "Export type is required"}), 400

    print(f"Received export request: Type='{export_type}', TimePeriod='{time_period}'")

    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    
    filename_base = ""
    df_data = [] # Initialize df_data here to ensure it's always available

    try:
        base_query = db.query(SurveySubmission).options(
            joinedload(SurveySubmission.survey).joinedload(Survey.questions).joinedload(Question.options),
            joinedload(SurveySubmission.answers).joinedload(Answer.question),
            joinedload(SurveySubmission.answers).joinedload(Answer.selected_option),
            joinedload(SurveySubmission.submitter),
            joinedload(SurveySubmission.submitter_department),
            joinedload(SurveySubmission.rated_department),
            joinedload(SurveySubmission.remark_responses).joinedload(RemarkResponse.responded_by_department)
        )
        filtered_submissions = filter_submissions_by_time_period_sql(db, time_period, base_query).all()

        if not filtered_submissions:
            # If no submissions, return early with a message. Don't try to create DataFrame.
            # Close writer even if no data is written to prevent resource leak
            writer.close() 
            return jsonify({"message": "No data found for the selected filter."}), 200

        # --- My Submitted Surveys Export ---
        if export_type == 'My Submitted Surveys':
            current_username = get_jwt_identity()
            current_user = db.query(User).filter(User.username == current_username).first()
            
            if not current_user:
                # Close writer before returning if user not found
                writer.close()
                return jsonify({"detail": "User not found for export filter"}), 404

            user_submissions = [
                sub for sub in filtered_submissions if sub.submitter_user_id == current_user.id
            ]

            if not user_submissions:
                writer.close()
                return jsonify({"message": "No 'My Submitted Surveys' data found for the selected filter and user."}), 200

            for submission in user_submissions:
                for answer in submission.answers:
                    if answer.question: # Ensure question exists
                        df_data.append({
                            "Survey ID": submission.id,
                            "Survey Title": submission.survey.title if submission.survey else 'N/A',
                            "Department Rated": submission.rated_department.name if submission.rated_department else 'N/A',
                            "Submitted By User": submission.submitter.username if submission.submitter else 'N/A',
                            "Submitted By Name": submission.submitter.name if submission.submitter else 'N/A',
                            "Submitted By Dept": submission.submitter_department.name if submission.submitter_department else 'N/A',
                            "Date": submission.submitted_at.strftime('%Y-%m-%d') if submission.submitted_at else 'N/A',
                            "Question Category": answer.question.category if answer.question else 'N/A',
                            "Question": answer.question.text,
                            "Question Type": answer.question.type,
                            "Rating (1-5)": answer.rating_value if answer.rating_value is not None else 'N/A',
                            "Selected Option": answer.selected_option.text if answer.selected_option else 'N/A',
                            "Remarks": answer.text_response if answer.text_response else 'N/A',
                            "Overall Rating (%)": submission.overall_customer_rating if submission.overall_customer_rating is not None else 'N/A',
                            "Rating Description": submission.rating_description if submission.rating_description else 'N/A',
                            "Suggestions": submission.suggestions if submission.suggestions else 'N/A'
                        })
            filename_base = "my_submitted_surveys"
            df = pd.DataFrame(df_data)
            df.to_excel(writer, sheet_name='My Submitted Surveys', index=False)


        # --- Department Ratings Export ---
        elif export_type == 'Department Ratings':
            department_summary = {}
            for submission in filtered_submissions:
                rated_dept_id = submission.rated_department_id
                if rated_dept_id not in department_summary:
                    department_summary[rated_dept_id] = {
                        "Department Name": submission.rated_department.name if submission.rated_department else rated_dept_id,
                        "Total Overall Rating": 0,
                        "Count": 0,
                        "Avg Quality": [], "Avg Delivery": [], "Avg Communication": [],
                        "Avg Responsiveness": [], "Avg Improvement": []
                    }
                
                if isinstance(submission.overall_customer_rating, (int, float)):
                    department_summary[rated_dept_id]["Total Overall Rating"] += submission.overall_customer_rating
                    department_summary[rated_dept_id]["Count"] += 1
                
                # Collect individual question ratings by category
                for answer in submission.answers:
                    if answer.question and answer.question.category and answer.rating_value is not None:
                        # Assuming categories are fixed as per your previous mock data structure
                        if answer.question.category == "Quality":
                            department_summary[rated_dept_id]["Avg Quality"].append(answer.rating_value)
                        elif answer.question.category == "Delivery":
                            department_summary[rated_dept_id]["Avg Delivery"].append(answer.rating_value)
                        elif answer.question.category == "Communication":
                            department_summary[rated_dept_id]["Avg Communication"].append(answer.rating_value)
                        elif answer.question.category == "Responsiveness":
                            department_summary[rated_dept_id]["Avg Responsiveness"].append(answer.rating_value)
                        elif answer.question.category == "Improvement":
                            department_summary[rated_dept_id]["Avg Improvement"].append(answer.rating_value)
                
            for dept_id, data in department_summary.items():
                avg_overall = round(data["Total Overall Rating"] / data["Count"], 2) if data["Count"] > 0 else 0.0
                rating_description = get_rating_description(avg_overall) # Use the helper function

                df_data.append({
                    "Department ID": dept_id,
                    "Department Name": data["Department Name"],
                    "Average Overall Rating (%)": avg_overall,
                    "Rating Description": rating_description,
                    "Average Quality (1-5)": round(sum(data["Avg Quality"]) / len(data["Avg Quality"]), 2) if data["Avg Quality"] else 0.0,
                    "Average Delivery (1-5)": round(sum(data["Avg Delivery"]) / len(data["Avg Delivery"]), 2) if data["Avg Delivery"] else 0.0,
                    "Average Communication (1-5)": round(sum(data["Avg Communication"]) / len(data["Avg Communication"]), 2) if data["Avg Communication"] else 0.0,
                    "Average Responsiveness (1-5)": round(sum(data["Avg Responsiveness"]) / len(data["Avg Responsiveness"]), 2) if data["Avg Responsiveness"] else 0.0,
                    "Average Improvement (1-5)": round(sum(data["Avg Improvement"]) / len(data["Avg Improvement"]), 2) if data["Avg Improvement"] else 0.0,
                    "Number of Surveys": data["Count"]
                })
            
            if not df_data: # If department_summary was empty, df_data will be empty
                writer.close()
                return jsonify({"message": "No 'Department Ratings' data found for the selected filter."}), 200

            filename_base = "department_ratings"
            df = pd.DataFrame(df_data)
            df.to_excel(writer, sheet_name='Department Ratings', index=False)


        # --- Submitted Remarks Only Export ---
        elif export_type == 'Submitted Remarks Only':
            for submission in filtered_submissions:
                # Add individual question remarks
                for answer in submission.answers:
                    if answer.text_response: # Only include answers with remarks
                        # Find associated response for this specific remark
                        found_response = next(
                            (r for r in submission.remark_responses if r.question_id == answer.question_id),
                            None
                        )
                        df_data.append({
                            "Survey ID": submission.id,
                            "Survey Title": submission.survey.title if submission.survey else 'N/A',
                            "Department Rated": submission.rated_department.name if submission.rated_department else 'N/A',
                            "Submitted By User": submission.submitter.username if submission.submitter else 'N/A',
                            "Submitted By Dept": submission.submitter_department.name if submission.submitter_department else 'N/A',
                            "Date": submission.submitted_at.strftime('%Y-%m-%d') if submission.submitted_at else 'N/A',
                            "Question Category": answer.question.category if answer.question else 'N/A',
                            "Question": answer.question.text if answer.question else 'N/A',
                            "Rating (1-5)": answer.rating_value if answer.rating_value is not None else 'N/A',
                            "Remarks": answer.text_response,
                            "Response Explanation": found_response.explanation if found_response else 'N/A',
                            "Response Action Plan": found_response.action_plan if found_response else 'N/A',
                            "Response Responsible Person": found_response.responsible_person if found_response else 'N/A',
                            "Response Date": found_response.responded_at.strftime('%Y-%m-%d') if found_response and found_response.responded_at else 'N/A',
                            "Responded By Dept": found_response.responded_by_department.name if found_response and found_response.responded_by_department else 'N/A',
                        })
                # Add overall suggestions
                if submission.suggestions:
                    df_data.append({
                        "Survey ID": submission.id,
                        "Survey Title": submission.survey.title if submission.survey else 'N/A',
                        "Department Rated": submission.rated_department.name if submission.rated_department else 'N/A',
                        "Submitted By User": submission.submitter.username if submission.submitter else 'N/A',
                        "Submitted By Dept": submission.submitter_department.name if submission.submitter_department else 'N/A',
                        "Date": submission.submitted_at.strftime('%Y-%m-%d') if submission.submitted_at else 'N/A',
                        "Question Category": "Overall Suggestion",
                        "Question": "Additional Suggestions or Feedback",
                        "Rating (1-5)": "N/A", 
                        "Remarks": submission.suggestions,
                        "Response Explanation": "N/A", # No direct response to overall suggestions
                        "Response Action Plan": "N/A",
                        "Response Responsible Person": "N/A",
                        "Response Date": "N/A",
                        "Responded By Dept": "N/A",
                    })
            
            if not df_data: # If no remarks or suggestions were found
                writer.close()
                return jsonify({"message": "No 'Submitted Remarks' data found for the selected filter."}), 200

            filename_base = "submitted_remarks"
            df = pd.DataFrame(df_data)
            df.to_excel(writer, sheet_name='Submitted Remarks', index=False)

        # --- Invalid Export Type ---
        else:
            writer.close() # Close writer for invalid type
            return jsonify({"detail": "Invalid export type"}), 400

        # These lines should always execute if a valid export_type was processed and a DataFrame was created
        writer.close() # Final close of the writer
        output.seek(0) # Reset stream position to the beginning

        current_date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        final_filename = f"{filename_base}_{current_date_str}.xlsx"

        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=final_filename)

    except Exception as e:
        db.rollback() # Rollback on error
        print(f"Error during Excel export for type {export_type}: {e}")
        # Always close writer on error if it was opened
        try:
            writer.close()
        except Exception as close_err:
            print(f"Error closing writer in exception handler: {close_err}")
        return jsonify({"detail": f"Server error during export: {str(e)}"}), 500
    finally:
        # db.close() is handled by get_db() context manager
        pass
