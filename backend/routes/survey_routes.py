# F:\LLS Survey\backend\routes\survey_routes.py
from flask import Blueprint, request, jsonify, abort, send_file
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case, and_
from database import SessionLocal
from models import Survey, Question, Option, SurveySubmission, Answer, RemarkResponse, Department, User
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError, NoResultFound
from datetime import datetime, timedelta
import pandas as pd
import io

survey_bp = Blueprint('survey', __name__, url_prefix='/api')

# Helper function to serialize Survey data (matching frontend SurveyData interface)
def serialize_survey(survey: Survey):
    questions_data = []
    for q in survey.questions:
        options_parsed = None
        if q.options:
            options_parsed = [{"id": opt.id, "text": opt.text, "value": opt.value} for opt in q.options]
        
        questions_data.append({
            "id": q.id,
            "text": q.text,
            "type": q.type,
            "order": q.order,
            "category": q.category,
            "options": options_parsed, 
        })
    return {
        "id": survey.id,
        "title": survey.title,
        "description": survey.description,
        "created_at": survey.created_at.isoformat() if survey.created_at else None,
        "rated_dept_name": survey.rated_department.name if survey.rated_department else None,
        "managing_dept_name": survey.managing_department.name if survey.managing_department else None,
        "rated_department_id": survey.rated_department_id,
        "managing_department_id": survey.managing_department_id,
        "questions": sorted(questions_data, key=lambda x: x['order']),
    }

# Helper function to serialize SurveySubmission (matching frontend SurveySubmission interface)
def serialize_submission_detailed(submission: SurveySubmission):
    return {
        "id": submission.id,
        "survey_id": submission.survey_id,
        "submitter_user_id": submission.submitter_user_id,
        "submitter_department_id": submission.submitter_department_id,
        "rated_department_id": submission.rated_department_id,
        "submitted_at": submission.submitted_at.isoformat() if submission.submitted_at else None,
        "overall_customer_rating": submission.overall_customer_rating,
        "rating_description": submission.rating_description,
        "suggestions": submission.suggestions,
        "submitter_department_name": submission.submitter_department.name if submission.submitter_department else None,
        "rated_department_name": submission.rated_department.name if submission.rated_department else None,
        "submitter_username": submission.submitter.username if submission.submitter else None,
    }


# Endpoint to get all active surveys (e.g., for Department Selection)
@survey_bp.route('/surveys', methods=['GET'])
# @jwt_required() # <-- COMMENTED OUT FOR DEVELOPMENT TO ALLOW PUBLIC ACCESS IF NEEDED BY FRONTEND BEFORE LOGIN
def get_surveys():
    db: Session = SessionLocal()
    try:
        surveys = db.query(Survey).options(
            joinedload(Survey.rated_department),
            joinedload(Survey.managing_department)
        ).all()
        return jsonify([serialize_survey(s) for s in surveys]), 200
    finally:
        db.close()

# Endpoint to get a specific survey by ID with its questions
@survey_bp.route('/surveys/<int:survey_id>', methods=['GET'])
# @jwt_required() # <-- COMMENTED OUT FOR DEVELOPMENT TO ALLOW PUBLIC ACCESS IF NEEDED BY FRONTEND BEFORE LOGIN
def get_survey_by_id(survey_id: int):
    db: Session = SessionLocal()
    try:
        survey = db.query(Survey).options(
            joinedload(Survey.questions).joinedload(Question.options),
            joinedload(Survey.rated_department),
            joinedload(Survey.managing_department)
        ).filter(Survey.id == survey_id).first()

        if not survey:
            return jsonify({"detail": "Survey not found"}), 404
        
        return jsonify(serialize_survey(survey)), 200
    finally:
        db.close()

# Endpoint to submit survey responses (ADAPTED FROM TEAMMATE'S '/submit-survey')
@survey_bp.route('/submit-survey', methods=['POST'])
@jwt_required() # This must remain protected
def submit_survey():
    db: Session = SessionLocal()
    try:
        data = request.get_json()

        required_fields = [
            'department_id', 'department_name', 'submitter_department_id', 'submitted_by',
            'date', 'questions_data', 'summary_metrics'
        ]
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        summary_metrics = data.get('summary_metrics', {})
        if 'overall_customer_rating' not in summary_metrics:
            return jsonify({"error": "Missing 'overall_customer_rating' in summary_metrics."}), 400
        try:
            overall_customer_rating = float(summary_metrics['overall_customer_rating'])
        except ValueError:
            return jsonify({"error": "overall_customer_rating in summary_metrics must be a number."}), 400

        rated_department = db.query(Department).filter(Department.id == data['department_id']).first()
        if not rated_department:
             return jsonify({"error": f"Rated Department with ID '{data['department_id']}' not found."}), 400

        submitter_department = db.query(Department).filter(Department.id == data['submitter_department_id']).first()
        if not submitter_department:
            return jsonify({"error": f"Submitter Department with ID '{data['submitter_department_id']}' not found."}), 400

        submitter_user = db.query(User).filter(User.username == data['submitted_by']).first()
        if not submitter_user:
            return jsonify({"error": f"Submitter user '{data['submitted_by']}' not found."}), 400

        submitted_at = datetime.strptime(data['date'], '%Y-%m-%d') if isinstance(data['date'], str) else datetime.utcnow()

        survey_template = db.query(Survey).filter(
            Survey.rated_department_id == rated_department.id
        ).first()

        if not survey_template:
            return jsonify({"error": f"No survey template found for rated department ID: {rated_department.id}"}), 400


        existing_submission = db.query(SurveySubmission).filter(
            SurveySubmission.survey_id == survey_template.id,
            SurveySubmission.submitter_user_id == submitter_user.id
        ).first()

        if existing_submission:
            return jsonify({"detail": "You have already submitted this survey."}), 409

        new_submission = SurveySubmission(
            survey_id=survey_template.id,
            submitter_user_id=submitter_user.id,
            submitter_department_id=submitter_department.id,
            rated_department_id=rated_department.id,
            submitted_at=submitted_at,
            overall_customer_rating=overall_customer_rating,
            rating_description=summary_metrics.get('rating_description'),
            suggestions=summary_metrics.get('suggestions')
        )
        db.add(new_submission)
        db.flush()

        for q_data in data.get('questions_data', []):
            question_id_from_payload = q_data.get('id')
            question_text = q_data.get('question')
            question_category = q_data.get('category')
            
            question_obj = None
            if isinstance(question_id_from_payload, int):
                question_obj = db.query(Question).filter(
                    Question.id == question_id_from_payload,
                    Question.survey_id == survey_template.id
                ).first()
            
            if not question_obj and question_text:
                question_obj = db.query(Question).filter(
                    Question.text == question_text,
                    Question.survey_id == survey_template.id
                ).first()

            if not question_obj:
                print(f"Warning: Question '{question_text}' (ID: {question_id_from_payload}) not found in template {survey_template.id}. Skipping answer.")
                continue

            new_answer = Answer(
                submission_id=new_submission.id,
                question_id=question_obj.id,
                rating_value=q_data.get('rating'),
                text_response=q_data.get('remarks'),
            )
            db.add(new_answer)
        
        db.commit()
        return jsonify({"message": "Survey submitted successfully!", "id": new_submission.id}), 201

    except IntegrityError as e:
        db.rollback()
        print(f"IntegrityError during survey submission: {e}")
        return jsonify({"detail": "Database integrity error. Possible duplicate submission or invalid data."}), 400
    except NoResultFound:
        db.rollback()
        return jsonify({"detail": "Required data (user/department/survey) not found in database."}), 400
    except Exception as e:
        db.rollback()
        print(f"Error submitting survey: {e}")
        return jsonify({"detail": f"An error occurred during submission: {str(e)}"}), 500
    finally:
        db.close()


# Endpoint to fetch incoming remarks for a department
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
                if answer.text_response:
                    remark_response_exists = db.query(RemarkResponse).filter(
                        RemarkResponse.survey_submission_id == submission.id,
                        RemarkResponse.question_id == answer.question_id
                    ).first()

                    if not remark_response_exists:
                        submission_date_str = submission.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if submission.submitted_at else None
                        
                        incoming_remarks.append({
                            "id": submission.id,
                            "questionDataId": answer.question_id,
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

# Endpoint to fetch outgoing remarks for a department
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
            joinedload(SurveySubmission.remark_responses)
        ).filter(
            SurveySubmission.submitter_department_id == my_department_id
        ).all()

        for submission in submissions:
            rated_department_name = submission.rated_department.name if submission.rated_department else 'Unknown Department'
            submission_date_str = submission.submitted_at.strftime('%Y-%m-%d %H:%M:%S') if submission.submitted_at else None

            for answer in submission.answers:
                if answer.text_response:
                    
                    their_response = {
                        "explanation": "",
                        "actionPlan": "",
                        "responsiblePerson": ""
                    }
                    found_response = next(
                        (r for r in submission.remark_responses if r.question_id == answer.question_id),
                        None
                    )
                    
                    if found_response:
                        their_response = {
                            "explanation": found_response.explanation,
                            "actionPlan": found_response.action_plan,
                            "responsiblePerson": found_response.responsible_person,
                        }
                    
                    outgoing_remarks.append({
                        "id": submission.id,
                        "questionDataId": answer.question_id,
                        "department": rated_department_name,
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


# Endpoint to submit a response to an incoming remark
@survey_bp.route('/remarks/respond', methods=['POST'])
@jwt_required() # This must remain protected
def respond_to_remark():
    db: Session = SessionLocal()
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
        submission_id = data.get('survey_id')
        question_id = data.get('question_data_id')
        explanation = data.get('explanation')
        action_plan = data.get('action_plan')
        responsible_person = data.get('responsible_person')

        if not all([submission_id, question_id, explanation, action_plan, responsible_person]):
            return jsonify({"detail": "Missing required fields"}), 400

        submission = db.query(SurveySubmission).filter(
            SurveySubmission.id == submission_id,
            SurveySubmission.rated_department_id == responded_by_department_id
        ).first()

        if not submission:
            return jsonify({"detail": "Submission not found or not authorized to respond for this department."}), 404

        existing_remark_response = db.query(RemarkResponse).filter(
            RemarkResponse.survey_submission_id == submission_id,
            RemarkResponse.question_id == question_id
        ).first()

        if existing_remark_response:
            return jsonify({"message": "Remark already responded to."}), 200

        new_remark_response = RemarkResponse(
            survey_submission_id=submission_id,
            question_id=question_id,
            explanation=explanation,
            action_plan=action_plan,
            responsible_person=responsible_person,
            responded_by_department_id=responded_by_department_id
        )
        db.add(new_remark_response)
        db.commit()
        
        return jsonify({"message": "Response submitted successfully!"}), 200

    except IntegrityError as e:
        db.rollback()
        print(f"IntegrityError during remark response submission: {e}")
        return jsonify({"detail": "Database integrity error. Possible duplicate response or invalid data."}), 400
    except Exception as e:
        db.rollback()
        print(f"Error submitting remark response: {e}")
        return jsonify({"detail": f"An error occurred during response submission: {str(e)}"}), 500
    finally:
        db.close()


# Endpoint to fetch department-specific dashboard metrics
@survey_bp.route('/department-dashboard-metrics', methods=['GET'])
@jwt_required() # This must remain protected as it fetches sensitive aggregated data
def get_department_dashboard_metrics():
    db: Session = SessionLocal()
    try:
        all_departments = db.query(Department).all()
        all_departments_map = {dept.id: dept.name for dept in all_departments}

        department_metrics_from_submissions = db.query(
            SurveySubmission.rated_department_id,
            func.avg(SurveySubmission.overall_customer_rating).label('average_rating'),
            func.count(SurveySubmission.id).label('total_surveys_received')
        ).group_by(SurveySubmission.rated_department_id).all()

        metrics_by_id = {
            metric.rated_department_id: {
                "average_rating": round(metric.average_rating, 2),
                "total_surveys_received": metric.total_surveys_received
            }
            for metric in department_metrics_from_submissions
        }

        unresponded_counts_map = {}
        for dept in all_departments:
            remark_answers_for_dept = db.query(Answer).join(SurveySubmission).filter(
                SurveySubmission.rated_department_id == dept.id,
                Answer.text_response.isnot(None)
            ).all()

            count = 0
            for answer in remark_answers_for_dept:
                response_exists = db.query(RemarkResponse).filter(
                    RemarkResponse.survey_submission_id == answer.submission_id,
                    RemarkResponse.question_id == answer.question_id
                ).first()
                if not response_exists:
                    count += 1
            unresponded_counts_map[dept.id] = count

        final_department_metrics = []
        for dept_id, dept_name in all_departments_map.items():
            metrics = metrics_by_id.get(dept_id, {"average_rating": 0.0, "total_surveys_received": 0})
            
            final_department_metrics.append({
                "department_id": dept_id,
                "department_name": dept_name,
                "average_rating_received": metrics['average_rating'],
                "total_surveys_received": metrics['total_surveys_received'],
                "unresponded_remarks_count": unresponded_counts_map.get(dept_id, 0),
            })
        
        final_department_metrics.sort(key=lambda x: x['department_name'])

        if not final_department_metrics:
            return jsonify([]), 200

        return jsonify(final_department_metrics), 200
    except Exception as e:
        print(f"Error fetching department dashboard metrics: {e}")
        return jsonify({"detail": f"Error fetching department dashboard metrics: {str(e)}"}), 500
    finally:
        db.close()


# Endpoint to get stored survey results for dashboard overview
@survey_bp.route('/stored-survey-results', methods=['GET'])
@jwt_required() # This must remain protected as it fetches sensitive data
def get_stored_survey_results_dashboard():
    db: Session = SessionLocal()
    try:
        recent_submissions = db.query(SurveySubmission).options(
            joinedload(SurveySubmission.rated_department),
            joinedload(SurveySubmission.submitter)
        ).order_by(SurveySubmission.submitted_at.desc()).limit(20).all()

        results = []
        for sub in recent_submissions:
            results.append({
                "id": sub.id,
                "departmentId": sub.rated_department_id,
                "submissionDate": sub.submitted_at.strftime('%Y-%m-%d') if sub.submitted_at else 'N/A',
                "overallRating": float(sub.overall_customer_rating) if sub.overall_customer_rating is not None else 0.0,
                "departmentName": sub.rated_department.name if sub.rated_department else 'N/A',
                "submitterUsername": sub.submitter.username if sub.submitter else 'N/A'
            })
        return jsonify(results), 200
    except Exception as e:
        print(f"Error fetching stored survey results dashboard: {e}")
        return jsonify({"detail": f"Error fetching stored survey results dashboard: {str(e)}"}), 500
    finally:
        db.close()


# Endpoint to get global survey summaries
@survey_bp.route('/submitted-survey-summaries', methods=['GET'])
@jwt_required() # This must remain protected as it fetches sensitive aggregated data
def get_global_survey_summaries():
    db: Session = SessionLocal()
    try:
        total_surveys = db.query(SurveySubmission).count()

        average_rating_result = db.query(
            func.avg(SurveySubmission.overall_customer_rating)
        ).scalar()
        average_overall_rating = round(average_rating_result, 2) if average_rating_result is not None else 0.0

        total_percentage = (average_overall_rating / 100.0) * 100 if average_overall_rating is not None else 0.0

        latest_submissions = []
        recent_subs_query = db.query(SurveySubmission).options(
            joinedload(SurveySubmission.rated_department)
        ).order_by(SurveySubmission.submitted_at.desc()).limit(5).all()

        for sub in recent_subs_query:
            latest_submissions.append({
                "id": sub.id,
                "departmentId": sub.rated_department_id,
                "overallRating": float(sub.overall_customer_rating) if sub.overall_customer_rating is not None else 0.0,
                "submissionDate": sub.submitted_at.strftime('%Y-%m-%d') if sub.submitted_at else 'N/A',
                "departmentName": sub.rated_department.name if sub.rated_department else 'N/A'
            })

        summary_data = {
            "totalSubmissions": total_surveys,
            "averageOverallRating": average_overall_rating,
            "totalPercentage": round(total_percentage, 2),
            "latestSubmissions": latest_submissions
        }
        return jsonify(summary_data), 200
    except Exception as e:
        print(f"Error fetching global survey summaries: {e}")
        return jsonify({"detail": f"Error fetching global survey summaries: {str(e)}"}), 500
    finally:
        db.close()


# Endpoint to export data to Excel
@survey_bp.route('/export', methods=['GET'])
@jwt_required() # This must remain protected as it handles sensitive data export
def export_excel():
    db: Session = SessionLocal()
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='openpyxl')
    
    export_type = request.args.get('type')
    time_period = request.args.get('timePeriod', 'all_time')

    if not export_type:
        return jsonify({"detail": "Export type is required"}), 400

    print(f"Received export request: Type='{export_type}', TimePeriod='{time_period}'")

    try:
        start_date = None
        current_date = datetime.utcnow().date()

        if time_period == "last_30_days":
            start_date = current_date - timedelta(days=30)
        elif time_period == "last_3_months":
            start_date = current_date - timedelta(days=90)
        elif time_period == "last_6_months":
            start_date = current_date - timedelta(days=180)
        elif time_period == "last_year":
            start_date = current_date - timedelta(days=365)
        
        query = db.query(SurveySubmission).options(
            joinedload(SurveySubmission.survey).joinedload(Survey.questions).joinedload(Question.options),
            joinedload(SurveySubmission.answers).joinedload(Answer.question),
            joinedload(SurveySubmission.answers).joinedload(Answer.selected_option),
            joinedload(SurveySubmission.submitter),
            joinedload(SurveySubmission.submitter_department),
            joinedload(SurveySubmission.rated_department),
            joinedload(SurveySubmission.remark_responses).joinedload(RemarkResponse.responded_by_department)
        )

        if start_date:
            query = query.filter(SurveySubmission.submitted_at >= start_date)

        all_submissions = query.order_by(SurveySubmission.submitted_at.desc()).all()

        df_data = []
        filename_base = ""

        if export_type == 'My Submitted Surveys':
            current_username = get_jwt_identity()
            current_user = db.query(User).filter(User.username == current_username).first()
            
            if not current_user:
                return jsonify({"detail": "User not found for export filter"}), 404

            user_submissions = [
                sub for sub in all_submissions if sub.submitter_user_id == current_user.id
            ]

            if not user_submissions:
                return jsonify({"message": "No 'My Submitted Surveys' data found for the selected filter and user."}), 200

            for submission in user_submissions:
                for answer in submission.answers:
                    if answer.question:
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

        elif export_type == 'Department Ratings':
            department_summary = {}
            for submission in all_submissions:
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
                
                category_ratings = {
                    "Quality": [], "Delivery": [], "Communication": [],
                    "Responsiveness": [], "Improvement": []
                }
                for answer in submission.answers:
                    if answer.question and answer.question.category and answer.rating_value is not None:
                        if answer.question.category in category_ratings:
                            category_ratings[answer.question.category].append(answer.rating_value)
                
                for cat, ratings_list in category_ratings.items():
                    if ratings_list:
                        department_summary[rated_dept_id][f"Avg {cat}"].append(sum(ratings_list) / len(ratings_list))

            for dept_id, data in department_summary.items():
                avg_overall = round(data["Total Overall Rating"] / data["Count"], 2) if data["Count"] > 0 else 0.0
                
                rating_description = ""
                if avg_overall >= 91: rating_description = "Excellent - Exceeds the Customer Expectation"
                elif avg_overall >= 75: rating_description = "Satisfactory - Meets the Customer requirement"
                elif avg_overall >= 70: rating_description = "Below Average - Identify areas for improvement and initiate action to eliminate dissatisfaction"
                else: rating_description = "Poor - Identify areas for improvement and initiate action to eliminate dissatisfaction"

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
            if not df_data:
                return jsonify({"message": "No 'Department Ratings' data found for the selected filter."}), 200
            df = pd.DataFrame(df_data)
            df.to_excel(writer, sheet_name='Department Ratings', index=False)
            filename_base = "department_ratings"

        elif export_type == 'Submitted Remarks Only':
            for submission in all_submissions:
                for answer in submission.answers:
                    if answer.text_response:
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
                            "Response Explanation": next((r.explanation for r in submission.remark_responses if r.question_id == answer.question_id), 'N/A'),
                            "Response Action Plan": next((r.action_plan for r in submission.remark_responses if r.question_id == answer.question_id), 'N/A'),
                            "Response Responsible Person": next((r.responsible_person for r in submission.remark_responses if r.question_id == answer.question_id), 'N/A'),
                            "Response Date": next((r.responded_at.strftime('%Y-%m-%d') for r in submission.remark_responses if r.question_id == answer.question_id and r.responded_at), 'N/A'),
                            "Responded By Dept": next((r.responded_by_department.name for r in submission.remark_responses if r.question_id == answer.question_id and r.responded_by_department), 'N/A'),
                        })
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
                        "Response Explanation": "N/A",
                        "Response Action Plan": "N/A",
                        "Response Responsible Person": "N/A",
                        "Response Date": "N/A",
                        "Responded By Dept": "N/A",
                    })
            if not df_data:
                return jsonify({"message": "No 'Submitted Remarks' data found for the selected filter."}), 200
            df = pd.DataFrame(df_data)
            df.to_excel(writer, sheet_name='Submitted Remarks', index=False)
            filename_base = "submitted_remarks"
        else:
            return jsonify({"detail": "Invalid export type"}), 400

        if not df_data:
            return jsonify({"message": f"No data found for export type '{export_type}' and time period '{time_period}'."}), 200


        writer.close()
        output.seek(0)

        current_date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        final_filename = f"{filename_base}_{current_date_str}.xlsx"

        return send_file(output,
                         mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True,
                         download_name=final_filename)

    except Exception as e:
        print(f"Error during Excel export for type {export_type}: {e}")
        db.rollback()
        return jsonify({"detail": f"Server error during export: {str(e)}"}), 500
    finally:
        db.close()
