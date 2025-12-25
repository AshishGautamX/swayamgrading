# website/routes/grading.py
"""
Grading routes for the AIGrader application.
Handles AI grading functionality.
"""

import json
import logging
import io
from threading import Thread
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user

from . import views
from ..models import Assignment, Submission, Rubric, GradingJob, db, check_resource_access
from ..services.ai_grading import get_ai_grading_service
from ..utils.helpers import clean_ai_response, extract_grade, extract_section

logger = logging.getLogger(__name__)


@views.route('/grade', methods=['POST'])
@login_required
def grade_assignment():
    """
    API endpoint for grading assignments using AI with full rubric support.
    """
    data = request.json
    question = data.get("question")
    student_answer = data.get("student_answer")
    rubric_id = data.get("rubric_id")
    
    # Validate input
    if not question or not student_answer:
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Get rubric if provided
    rubric_criteria = []
    level = "High School"  # Default level
    if rubric_id:
        rubric = Rubric.query.get(rubric_id)
        if rubric:
            rubric_criteria = rubric.get_criteria()
            level = rubric.level
    
    try:
        ai_service = get_ai_grading_service()
        result = ai_service.grade_submission(question, student_answer, rubric_criteria, level)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error in grade_assignment: {str(e)}")
        return jsonify({'error': str(e)}), 500


@views.route('/extract-pdf-text', methods=['POST'])
@login_required
def extract_pdf_text():
    """
    Extract text from uploaded PDF files using PyPDF2.
    """
    try:
        from PyPDF2 import PdfReader
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'error': 'Only PDF files are supported'}), 400
        
        # Read PDF content
        pdf_reader = PdfReader(io.BytesIO(file.read()))
        extracted_text = ""
        
        for page in pdf_reader.pages:
            page_text = page.extract_text()
            if page_text:
                extracted_text += page_text + "\n"
        
        if not extracted_text.strip():
            return jsonify({
                'success': False,
                'error': 'Could not extract text from PDF. The PDF may be image-based.'
            }), 400
        
        return jsonify({
            'success': True,
            'text': extracted_text.strip(),
            'pages': len(pdf_reader.pages)
        })
        
    except Exception as e:
        logger.error(f"Error extracting PDF text: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@views.route('/deepgrade/<int:submission_id>', methods=['GET', 'POST'])
@login_required
def deepgrade(submission_id):
    """
    View for grading a specific submission using AI.
    """
    submission = Submission.query.get_or_404(submission_id)
    assignment = submission.assignment_ref
    
    # Security check
    if not check_resource_access(assignment.class_ref):
        flash('You do not have permission to grade this submission!', category='error')
        return redirect(url_for('views.dashboard'))
    
    rubric = Rubric.query.get(assignment.rubric_id) if assignment.rubric_id else None
    
    if request.method == 'POST':
        try:
            ai_service = get_ai_grading_service()
            rubric_criteria = rubric.get_criteria() if rubric else []
            result = ai_service.grade_submission(
                assignment.question, 
                submission.student_answer,
                rubric_criteria,
                rubric.level if rubric else "High School"
            )
            
            # Update submission with results
            grade_str = result.get('grade', '')
            if '/' in str(grade_str):
                try:
                    submission.grade = float(grade_str.split('/')[0])
                except:
                    submission.grade = 70
            else:
                submission.grade = float(grade_str) if grade_str else 70
            
            submission.feedback = result.get('feedback', '')
            db.session.commit()
            
            flash('Submission graded successfully!', category='success')
            
        except Exception as e:
            logger.error(f"Error in deepgrade: {str(e)}")
            flash(f'Error grading submission: {str(e)}', category='error')
    
    return render_template('deepgrade.html', 
                         submission=submission, 
                         assignment=assignment,
                         rubric=rubric,
                         user=current_user)


@views.route('/grade-all/<int:assignment_id>', methods=['POST'])
@login_required
def grade_all_submissions(assignment_id):
    """
    View for grading all submissions for a particular assignment using AI.
    Returns job ID for tracking progress.
    """
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Security check
    if not check_resource_access(assignment.class_ref):
        return jsonify({'error': 'Permission denied'}), 403
    
    # Get ungraded submissions
    submissions = Submission.query.filter_by(assignment_id=assignment_id).all()
    skip_graded = request.json.get('skip_graded', True) if request.json else True
    
    if skip_graded:
        submissions = [s for s in submissions if s.grade is None or s.feedback is None]
    
    if not submissions:
        return jsonify({'error': 'No submissions to grade'}), 400
    
    # Create a grading job
    job = GradingJob(
        assignment_id=assignment_id,
        user_id=current_user.id,
        total_count=len(submissions),
        processed_count=0,
        status='pending'
    )
    db.session.add(job)
    db.session.commit()
    
    # Start background grading
    submission_ids = [s.id for s in submissions]
    app = current_app._get_current_object()
    
    thread = Thread(target=process_grading_job, args=(app, job.id, submission_ids, assignment.rubric_id, skip_graded))
    thread.start()
    
    return jsonify({
        'success': True,
        'job_id': job.id,
        'total_count': len(submissions),
        'message': f'Started grading {len(submissions)} submissions'
    })


@views.route('/check-grading-status/<int:job_id>')
@login_required
def check_grading_status(job_id):
    """
    Route to check the status of a background grading job.
    Returns JSON with current progress, status message, and results.
    """
    job = GradingJob.query.get_or_404(job_id)
    
    # Security check
    if job.user_id != current_user.id:
        return jsonify({'error': 'Permission denied'}), 403
    
    return jsonify({
        'job_id': job.id,
        'status': job.status,
        'processed_count': job.processed_count,
        'total_count': job.total_count,
        'progress_percent': (job.processed_count / job.total_count * 100) if job.total_count > 0 else 0,
        'current_message': job.current_message or '',
        'completed': job.status == 'completed',
        'error': job.error_message if job.status == 'error' else None
    })


def process_grading_job(app, job_id, submission_ids, rubric_id, skip_graded=True):
    """
    Background function to process a grading job.
    Updates job status in the database as progress is made.
    """
    with app.app_context():
        job = GradingJob.query.get(job_id)
        if not job:
            return
        
        job.status = 'processing'
        db.session.commit()
        
        rubric = Rubric.query.get(rubric_id) if rubric_id else None
        ai_service = get_ai_grading_service()
        
        try:
            for i, submission_id in enumerate(submission_ids):
                submission = Submission.query.get(submission_id)
                if not submission:
                    continue
                
                # Skip if already graded and skip_graded is True
                if skip_graded and submission.grade is not None and submission.feedback:
                    job.processed_count += 1
                    job.current_message = f"Skipped {submission.student_name} (already graded)"
                    db.session.commit()
                    continue
                
                job.current_message = f"Grading submission from {submission.student_name}..."
                db.session.commit()
                
                assignment = submission.assignment_ref
                rubric_criteria = rubric.get_criteria() if rubric else []
                
                try:
                    result = ai_service.grade_submission(
                        assignment.question,
                        submission.student_answer,
                        rubric_criteria,
                        rubric.level if rubric else "High School"
                    )
                    
                    # Update submission
                    grade_str = result.get('grade', '70/100')
                    if '/' in str(grade_str):
                        try:
                            submission.grade = float(grade_str.split('/')[0])
                        except:
                            submission.grade = 70
                    else:
                        submission.grade = float(grade_str) if grade_str else 70
                    
                    submission.feedback = result.get('feedback', '')
                    
                except Exception as e:
                    logger.error(f"Error grading submission {submission_id}: {e}")
                    submission.feedback = f"Error during grading: {str(e)}"
                
                job.processed_count += 1
                db.session.commit()
            
            job.status = 'completed'
            job.current_message = 'All submissions graded successfully'
            db.session.commit()
            
        except Exception as e:
            logger.error(f"Error in grading job {job_id}: {e}")
            job.status = 'error'
            job.error_message = str(e)
            db.session.commit()
