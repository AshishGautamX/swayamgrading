# website/routes/google_integration.py
"""
Google Classroom integration routes for the AIGrader application.
Handles Google OAuth and Classroom API interactions.
"""

import os
import json
import logging
from flask import render_template, redirect, url_for, flash, request, jsonify, session
from flask_login import login_required, current_user
import google.oauth2.credentials
import google_auth_oauthlib.flow
import googleapiclient.discovery

from . import views
from ..models import Class, GoogleClass, Assignment, Submission, Rubric, db, check_resource_access

logger = logging.getLogger(__name__)

# OAuth Scopes
SCOPES = [
    'https://www.googleapis.com/auth/classroom.courses.readonly',
    'https://www.googleapis.com/auth/classroom.coursework.me',
    'https://www.googleapis.com/auth/classroom.coursework.students',
    'https://www.googleapis.com/auth/classroom.rosters.readonly',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/drive.readonly',
    'openid'
]


def get_google_credentials():
    """
    Helper function to get refreshed Google credentials.
    Returns None if credentials are not available or refresh fails.
    """
    if not current_user.google_tokens:
        logger.warning("No Google tokens found for user")
        return None
    
    try:
        token_data = json.loads(current_user.google_tokens)
        
        # Check if we have all required fields for refreshing
        required_fields = ['refresh_token', 'token_uri', 'client_id', 'client_secret']
        missing_fields = [field for field in required_fields if field not in token_data or not token_data[field]]
        
        if missing_fields:
            logger.warning(f"Missing required fields for token refresh: {', '.join(missing_fields)}")
            return None
        
        credentials = google.oauth2.credentials.Credentials(
            token=token_data.get('token'),
            refresh_token=token_data.get('refresh_token'),
            token_uri=token_data.get('token_uri'),
            client_id=token_data.get('client_id'),
            client_secret=token_data.get('client_secret'),
            scopes=token_data.get('scopes')
        )
        
        # Force refresh if token is expired
        if not credentials.valid:
            logger.info("Token expired, attempting to refresh")
            import google.auth.transport.requests
            auth_request = google.auth.transport.requests.Request()
            credentials.refresh(auth_request)
            
            # Update stored token
            current_user.google_tokens = json.dumps({
                'token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'token_uri': credentials.token_uri,
                'client_id': credentials.client_id,
                'client_secret': credentials.client_secret,
                'scopes': credentials.scopes
            })
            db.session.commit()
            logger.info("Token refreshed successfully")
        
        return credentials
    except Exception as e:
        logger.error(f"Error refreshing credentials: {str(e)}")
        return None


@views.route('/import-google-classroom', endpoint='import_google_classroom')
@login_required
def import_google_classroom():
    """Initiate Google Classroom OAuth flow."""
    try:
        # Use the client secret JSON directly from environment variable
        client_secret_json = json.loads(os.getenv("CLIENT_SECRET_JSON", "{}"))
        
        if not client_secret_json:
            flash('Google Classroom integration is not configured.', 'error')
            return redirect(url_for('views.dashboard'))
        
        # Create a flow from the client secret json dictionary
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            client_secret_json, scopes=SCOPES)
        flow.redirect_uri = url_for('views.oauth2callback', _external=True)
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent')
        session['state'] = state
        return redirect(authorization_url)
    except Exception as e:
        logger.error(f"Error initiating Google OAuth: {e}")
        flash(f'Error connecting to Google: {str(e)}', 'error')
        return redirect(url_for('views.dashboard'))


@views.route('/oauth2callback', endpoint='oauth2callback')
@login_required
def oauth2callback():
    """Handle Google OAuth callback."""
    try:
        # Get state from session
        state = session.get('state')
        if not state:
            flash('Authentication session expired. Please try again.', 'error')
            return redirect(url_for('views.dashboard'))
        
        # Use the client secret JSON directly from environment variable
        client_secret_json = json.loads(os.getenv("CLIENT_SECRET_JSON", "{}"))
        
        # Create flow from client config
        flow = google_auth_oauthlib.flow.Flow.from_client_config(
            client_secret_json, scopes=SCOPES, state=state)
        flow.redirect_uri = url_for('views.oauth2callback', _external=True)
        
        # Fetch token
        authorization_response = request.url
        flow.fetch_token(authorization_response=authorization_response)
        
        credentials = flow.credentials
        
        # Check for refresh token
        if not credentials.refresh_token:
            logger.warning("No refresh token received, redirecting to re-auth")
            return redirect(url_for('views.import_google_classroom'))
        
        token_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        
        # Store the tokens
        current_user.google_tokens = json.dumps(token_data)
        db.session.commit()
        
        return redirect(url_for('views.select_google_class'))
    except Exception as e:
        logger.error(f"Error during OAuth callback: {e}")
        flash(f'Error during authentication: {str(e)}', 'error')
        return redirect(url_for('views.dashboard'))


@views.route('/select-google-class', endpoint='select_google_class', methods=['GET', 'POST'])
@login_required
def select_google_class():
    """Select a Google Classroom class to import."""
    if request.method == 'POST':
        selected_class_id = request.form.get('class_id')
        return redirect(url_for('views.select_rubric', class_id=selected_class_id))
    
    # Get Google Classroom service
    credentials = get_google_credentials()
    if not credentials:
        flash('Please connect your Google account first.', 'error')
        return redirect(url_for('views.import_google_classroom'))
    
    try:
        service = googleapiclient.discovery.build('classroom', 'v1', credentials=credentials)
        results = service.courses().list(teacherId='me', courseStates=['ACTIVE']).execute()
        classes = results.get('courses', [])
        
        return render_template('select_google_class.html', classes=classes, user=current_user)
    except Exception as e:
        logger.error(f"Error fetching Google classes: {e}")
        flash(f'Error fetching classes: {str(e)}', 'error')
        return redirect(url_for('views.dashboard'))


@views.route('/select-rubric/<class_id>', methods=['GET', 'POST'])
@login_required
def select_rubric(class_id):
    """Select a rubric for the imported class."""
    if request.method == 'POST':
        rubric_id = request.form.get('rubric_id')
        class_name = request.form.get('class_name')
        level = request.form.get('class_level', 'High School')
        
        try:
            # Create the Google class
            new_class = GoogleClass(
                name=class_name or f"Google Class {class_id}",
                level=level,
                owner_id=current_user.id,
                google_class_id=class_id
            )
            db.session.add(new_class)
            db.session.commit()
            
            # Import assignments
            import_assignments_from_google(new_class.id)
            
            flash('Google Classroom class imported successfully!', 'success')
            return redirect(url_for('views.view_class', class_id=new_class.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error importing class: {e}")
            flash(f'Error importing class: {str(e)}', 'error')
            return redirect(url_for('views.dashboard'))
    
    # GET request - get class name from Google and show rubric selection
    credentials = get_google_credentials()
    if not credentials:
        return redirect(url_for('views.import_google_classroom'))
    
    try:
        service = googleapiclient.discovery.build('classroom', 'v1', credentials=credentials)
        course = service.courses().get(id=class_id).execute()
        class_name = course.get('name', f"Google Class {class_id}")
    except Exception as e:
        logger.error(f"Error fetching class details: {e}")
        class_name = f"Google Class {class_id}"
    
    rubrics = Rubric.query.filter(
        (Rubric.creator_id == current_user.id) | (Rubric.creator_id == None)
    ).all()
    
    return render_template('select_rubric.html', 
                         class_id=class_id, 
                         class_name=class_name,
                         rubrics=rubrics)


@views.route('/refresh-google-assignments/<int:class_id>', methods=['POST'])
@login_required
def refresh_google_assignments(class_id):
    """Refresh assignments from Google Classroom."""
    cls = GoogleClass.query.get_or_404(class_id)
    
    if not check_resource_access(cls):
        return jsonify({'error': 'Permission denied'}), 403
    
    try:
        import_assignments_from_google(class_id)
        return jsonify({'success': True, 'message': 'Assignments refreshed'})
    except Exception as e:
        logger.error(f"Error refreshing assignments: {e}")
        return jsonify({'error': str(e)}), 500


def import_assignments_from_google(class_id):
    """
    Helper function to import assignments from Google Classroom.
    """
    cls = GoogleClass.query.get(class_id)
    if not cls or not cls.google_class_id:
        return False
    
    credentials = get_google_credentials()
    if not credentials:
        return False
    
    try:
        service = googleapiclient.discovery.build('classroom', 'v1', credentials=credentials)
        
        # Get coursework
        courseworks = service.courses().courseWork().list(
            courseId=cls.google_class_id
        ).execute().get('courseWork', [])
        
        for coursework in courseworks:
            # Check if assignment already exists
            existing = Assignment.query.filter_by(
                class_id=class_id,
                name=coursework.get('title')
            ).first()
            
            if not existing:
                new_assignment = Assignment(
                    name=coursework.get('title', 'Untitled'),
                    question=coursework.get('description', 'No description'),
                    class_id=class_id,
                    rubric_id=None  # Can be set later
                )
                db.session.add(new_assignment)
        
        db.session.commit()
        return True
        
    except Exception as e:
        logger.error(f"Error importing assignments: {e}")
        db.session.rollback()
        return False


@views.route('/get-google-classroom-students/<int:class_id>')
@login_required
def get_google_classroom_students(class_id):
    """Get students from a Google Classroom class."""
    cls = GoogleClass.query.get_or_404(class_id)
    
    if not check_resource_access(cls):
        return jsonify({'error': 'Permission denied'}), 403
    
    credentials = get_google_credentials()
    if not credentials:
        return jsonify({'error': 'Google credentials not available'}), 401
    
    try:
        service = googleapiclient.discovery.build('classroom', 'v1', credentials=credentials)
        students = service.courses().students().list(
            courseId=cls.google_class_id
        ).execute().get('students', [])
        
        student_list = []
        for student in students:
            profile = student.get('profile', {})
            student_list.append({
                'id': student.get('userId'),
                'name': profile.get('name', {}).get('fullName', 'Unknown'),
                'email': profile.get('emailAddress', '')
            })
        
        return jsonify({'success': True, 'students': student_list})
        
    except Exception as e:
        logger.error(f"Error fetching students: {e}")
        return jsonify({'error': str(e)}), 500


@views.route('/view-attachment/<int:submission_id>/<file_id>')
@login_required
def view_attachment(submission_id, file_id):
    """View a Google Drive attachment."""
    submission = Submission.query.get_or_404(submission_id)
    
    if not check_resource_access(submission.assignment_ref.class_ref):
        flash('Permission denied', 'error')
        return redirect(url_for('views.dashboard'))
    
    credentials = get_google_credentials()
    if not credentials:
        flash('Google credentials not available', 'error')
        return redirect(url_for('views.dashboard'))
    
    try:
        service = googleapiclient.discovery.build('drive', 'v3', credentials=credentials)
        
        # Get file metadata
        file_metadata = service.files().get(
            fileId=file_id,
            fields='name,mimeType,webViewLink'
        ).execute()
        
        # Redirect to Google Drive view
        return redirect(file_metadata.get('webViewLink', url_for('views.dashboard')))
        
    except Exception as e:
        logger.error(f"Error viewing attachment: {e}")
        flash(f'Error viewing attachment: {str(e)}', 'error')
        return redirect(url_for('views.dashboard'))


@views.route('/get-extracted-text/<int:submission_id>/<file_id>', endpoint='get_extracted_text')
@login_required
def get_extracted_text(submission_id, file_id):
    """Get the extracted text from a specific file attachment."""
    submission = Submission.query.get(submission_id)
    
    if not submission or not submission.assignment_ref:
        return jsonify({"error": "Submission not found"}), 404
    
    if not check_resource_access(submission.assignment_ref.class_ref):
        return jsonify({"error": "Permission denied"}), 403
    
    try:
        # Check if submission has submission_data
        if not hasattr(submission, 'submission_data') or not submission.submission_data:
            return jsonify({"error": "No file data available"}), 404
        
        submission_data = json.loads(submission.submission_data)
        
        # Find the specific file
        for file in submission_data.get('files', []):
            if file.get('id') == file_id:
                # Look for extracted text
                if submission.student_answer:
                    marker = f"--- Text extracted from {file.get('name')} ---"
                    if marker in submission.student_answer:
                        parts = submission.student_answer.split(marker)
                        for i, part in enumerate(parts):
                            if i > 0:
                                extracted_text = part.split("--- Text extracted from")[0] if "--- Text extracted from" in part else part
                                return jsonify({"text": extracted_text.strip()})
                
                return jsonify({"error": "No extracted text found for this file"}), 404
        
        return jsonify({"error": "File not found in submission data"}), 404
        
    except Exception as e:
        logger.error(f"Error getting extracted text: {e}")
        return jsonify({"error": str(e)}), 500
