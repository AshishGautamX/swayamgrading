# website/routes/submissions.py
"""
Submission routes for the AIGrader application.
Handles student submission management.
"""

import logging
import urllib.parse
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from . import views
from ..models import Assignment, Submission, db, check_resource_access
from ..utils.validators import validate_text_field, validate_email

logger = logging.getLogger(__name__)


@views.route('/add-submission/<int:assignment_id>', methods=['GET', 'POST'])
@login_required
def add_submission(assignment_id):
    """Add a new submission for an assignment."""
    assignment = Assignment.query.get_or_404(assignment_id)
    
    # Security: Check if user owns the class this assignment belongs to
    if not check_resource_access(assignment.class_ref):
        flash('You do not have permission to add submissions to this assignment!', category='error')
        return redirect(url_for('views.dashboard'))
    
    if request.method == 'POST':
        student_name = request.form.get('student_name')
        student_email = request.form.get('student_email')
        student_answer = request.form.get('student_answer')
        
        # Input validation
        valid, result = validate_text_field(student_name, 'Student name', max_length=150)
        if not valid:
            flash(result, category='error')
            return redirect(url_for('views.view_class', class_id=assignment.class_id))
        student_name = result
        
        valid, result = validate_email(student_email)
        if not valid:
            flash(result, category='error')
            return redirect(url_for('views.view_class', class_id=assignment.class_id))
        student_email = result
        
        valid, result = validate_text_field(student_answer, 'Student answer')
        if not valid:
            flash(result, category='error')
            return redirect(url_for('views.view_class', class_id=assignment.class_id))
        student_answer = result
        
        # Create new submission
        new_submission = Submission(
            student_name=student_name,
            student_email=student_email,
            student_answer=student_answer,
            assignment_id=assignment.id,
            student_id=current_user.id
        )
        
        db.session.add(new_submission)
        db.session.commit()
        
        flash('Submission added successfully!', category='success')
        return redirect(url_for('views.view_class', class_id=assignment.class_id))
    
    # If GET request, render the form dialog
    return render_template('add_submission.html', assignment=assignment)


@views.route('/delete-submission/<int:submission_id>', methods=['POST'])
@login_required
def delete_submission(submission_id):
    """Delete a submission."""
    submission = Submission.query.get_or_404(submission_id)
    class_id = submission.assignment_ref.class_id
    
    # Security check
    if not check_resource_access(submission.assignment_ref.class_ref):
        flash('You do not have permission to delete this submission!', category='error')
        return redirect(url_for('views.dashboard'))
    
    try:
        db.session.delete(submission)
        db.session.commit()
        flash('Submission deleted successfully!', category='success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting submission: ' + str(e), category='error')
    
    return redirect(url_for('views.view_class', class_id=class_id))


@views.route('/update-student-email/<submission_id>', methods=['POST'])
@login_required
def update_student_email(submission_id):
    """Update a student's email for a submission."""
    try:
        submission = Submission.query.get_or_404(submission_id)
        
        # Security: Check if user owns the class this submission belongs to
        if not check_resource_access(submission.assignment_ref.class_ref):
            return jsonify({'error': 'Permission denied'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email')
        
        # Validate email
        valid, result = validate_email(email)
        if not valid:
            return jsonify({'error': result}), 400
        
        # Update the submission with the new email
        submission.student_email = result
        db.session.commit()
        
        logger.info(f"User {current_user.id} updated email for submission {submission_id}")
        return jsonify({'success': True, 'message': 'Email updated successfully'})
    except Exception as e:
        logger.error(f"Error updating student email: {str(e)}")
        return jsonify({'error': str(e)}), 400


@views.route('/send-grade/<int:submission_id>')
@login_required
def send_grade(submission_id):
    """
    Redirect to Gmail with pre-filled email content to send the grade to a student.
    """
    submission = Submission.query.get_or_404(submission_id)
    
    # Security check
    if not check_resource_access(submission.assignment_ref.class_ref):
        flash('You do not have permission to send grades for this submission!', category='error')
        return redirect(url_for('views.dashboard'))
    
    assignment = submission.assignment_ref
    
    # Build email subject
    subject = f"Grade for {assignment.name}"
    
    # Build email body
    body = f"""Dear {submission.student_name},

Here is your feedback for the assignment "{assignment.name}":

Grade: {submission.grade if submission.grade else 'Not graded yet'}

Feedback:
{submission.feedback if submission.feedback else 'No feedback available yet.'}

Best regards,
{current_user.email}
"""
    
    # URL encode the email parameters
    encoded_subject = urllib.parse.quote(subject)
    encoded_body = urllib.parse.quote(body)
    
    # Build Gmail compose URL
    gmail_url = f"https://mail.google.com/mail/?view=cm&fs=1&to={submission.student_email}&su={encoded_subject}&body={encoded_body}"
    
    return redirect(gmail_url)
