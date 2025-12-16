from .import db
from flask_login import UserMixin
import json
from datetime import datetime
from functools import wraps
from flask import flash, redirect, url_for
from flask_login import current_user

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True)
    password = db.Column(db.String(150))
    name = db.Column(db.String(150))
    google_id = db.Column(db.String(150))
    is_teacher = db.Column(db.Boolean, default=False)
    classes = db.relationship('Class', 
                          backref='owner', 
                          lazy=True, 
                          foreign_keys='Class.owner_id')
    rubrics = db.relationship('Rubric', backref='creator', lazy=True)
    google_tokens = db.Column(db.Text)  # Store Google OAuth tokens

class Class(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    level = db.Column(db.String(50))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_class_user'))
    type = db.Column(db.String(20), nullable=False, default='manual')  # Add default value
    __mapper_args__ = {'polymorphic_on': type}

    # Common relationships
    assignments = db.relationship('Assignment', backref='class_ref', lazy=True)

class ManualClass(Class):
    __mapper_args__ = {'polymorphic_identity': 'manual'}

class GoogleClass(Class):
    google_classroom_id = db.Column(db.String(150))
    rubric_id = db.Column(db.Integer, db.ForeignKey('rubric.id', name='fk_googleclass_rubric'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_googleclass_user'))  # Added user_id
    __mapper_args__ = {'polymorphic_identity': 'google'}
    rubric = db.relationship('Rubric', backref='google_classes')
    user = db.relationship('User', 
                       backref='google_classes', foreign_keys=[user_id]) 

class Assignment(db.Model):
    __tablename__ = 'assignment'  # Explicitly define the table name
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    question = db.Column(db.Text)
    standard_answer = db.Column(db.Text)
    rubric_id = db.Column(db.Integer, db.ForeignKey('rubric.id', name='fk_assignment_rubric'))
    class_id = db.Column(db.Integer, db.ForeignKey('class.id', name='fk_assignment_class'))
    submissions = db.relationship('Submission', backref='assignment_ref', lazy=True)
    rubric = db.relationship('Rubric', backref='assignments', lazy=True)

class Rubric(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150))
    description = db.Column(db.Text)
    level = db.Column(db.String(50))  # Primary, Middle School, High School
    criteria = db.Column(db.Text)  # JSON stored as text
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_rubric_user'))
    def get_criteria_dict(self):
        return json.loads(self.criteria)

    def get_criteria(self):
        """Get structured criteria based on level"""
        
        return {
            "Primary": {
                "Concept Understanding": [
                    {"rating": "Excellent", "score": 5, "description": "Fully understands and applies concepts correctly."},
                    {"rating": "Good", "score": 4, "description": "Understands but makes minor mistakes."},
                    {"rating": "Satisfactory", "score": 3, "description": "Basic understanding, needs guidance."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Struggles to grasp concepts."},
                    {"rating": "Poor", "score": 1, "description": "Shows minimal understanding."}
                ],
                "Neatness & Presentation": [
                    {"rating": "Excellent", "score": 5, "description": "Work is neat, well-organized, and creative."},
                    {"rating": "Good", "score": 4, "description": "Generally neat with minor untidiness."},
                    {"rating": "Satisfactory", "score": 3, "description": "Presentation is okay but lacks clarity."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Untidy work, lacks effort."},
                    {"rating": "Poor", "score": 1, "description": "Poorly presented, difficult to read."}
                ],
                "Grammar & Language (For English/Hindi)": [
                    {"rating": "Excellent", "score": 5, "description": "No errors, excellent sentence formation."},
                    {"rating": "Good", "score": 4, "description": "Few errors, good sentence structure."},
                    {"rating": "Satisfactory", "score": 3, "description": "Some grammar mistakes, understandable."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Many errors, needs improvement."},
                    {"rating": "Poor", "score": 1, "description": "Numerous errors, difficult to understand."}
                ],
            },
            "Middle School": {
                "Concept Mastery": [
                    {"rating": "Excellent", "score": 5, "description": "Demonstrates in-depth understanding and applies concepts correctly."},
                    {"rating": "Good", "score": 4, "description": "Good understanding with minor errors."},
                    {"rating": "Satisfactory", "score": 3, "description": "Basic understanding but needs improvement."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Struggles to apply concepts accurately."},
                    {"rating": "Poor", "score": 1, "description": "Limited or no understanding."}
                ],
                "Problem-Solving Skills": [
                    {"rating": "Excellent", "score": 5, "description": "Accurately applies formulas and logic."},
                    {"rating": "Good", "score": 4, "description": "Minor calculation errors but good approach."},
                    {"rating": "Satisfactory", "score": 3, "description": "Needs guidance in approach."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Struggles with problem-solving."},
                    {"rating": "Poor", "score": 1, "description": "Incorrect or incomplete solutions."}
                ],
                "Creativity & Expression": [
                    {"rating": "Excellent", "score": 5, "description": "Highly creative and well-expressed ideas."},
                    {"rating": "Good", "score": 4, "description": "Good ideas with some originality."},
                    {"rating": "Satisfactory", "score": 3, "description": "Basic ideas with minimal creativity."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Lacks depth and originality."},
                    {"rating": "Poor", "score": 1, "description": "Unclear or copied work."}
                ],
                "Time Management & Submission": [
                    {"rating": "Excellent", "score": 5, "description": "Always submits on time, well-paced work."},
                    {"rating": "Good", "score": 4, "description": "Mostly on time with occasional delays."},
                    {"rating": "Satisfactory", "score": 3, "description": "Sometimes late, needs reminders."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Often late, incomplete work."},
                    {"rating": "Poor", "score": 1, "description": "Rarely submits on time."}
                ]
            },
            "High School": {
                "Subject Knowledge": [
                    {"rating": "Excellent", "score": 5, "description": "Deep understanding, integrates multiple concepts."},
                    {"rating": "Good", "score": 4, "description": "Good grasp but minor conceptual gaps."},
                    {"rating": "Satisfactory", "score": 3, "description": "Basic understanding, lacks depth."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Weak understanding, major errors."},
                    {"rating": "Poor", "score": 1, "description": "Minimal or no knowledge displayed."}
                ],
                "Application & Analysis": [
                    {"rating": "Excellent", "score": 5, "description": "Strong analytical skills, applies knowledge well."},
                    {"rating": "Good", "score": 4, "description": "Good analysis, applies concepts well."},
                    {"rating": "Satisfactory", "score": 3, "description": "Limited analysis, mostly factual."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Weak application, minimal analysis."},
                    {"rating": "Poor", "score": 1, "description": "No analysis, copied content."}
                ],
                "Answer Structure (For Written Exams)": [
                    {"rating": "Excellent", "score": 5, "description": "Well-structured, logical, follows CBSE format."},
                    {"rating": "Good", "score": 4, "description": "Mostly structured, minor inconsistencies."},
                    {"rating": "Satisfactory", "score": 3, "description": "Some structure but lacks coherence."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Unorganized, lacks clarity."},
                    {"rating": "Poor", "score": 1, "description": "No structure, difficult to follow."}
                ],
                "Use of Examples & Diagrams": [
                    {"rating": "Excellent", "score": 5, "description": "Relevant examples, clear diagrams, well-labeled."},
                    {"rating": "Good", "score": 4, "description": "Good examples, minor missing details."},
                    {"rating": "Satisfactory", "score": 3, "description": "Some examples but lacks clarity."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Few or incorrect examples."},
                    {"rating": "Poor", "score": 1, "description": "No examples or diagrams."}
                ],
                "Grammar & Writing Skills": [
                    {"rating": "Excellent", "score": 5, "description": "No grammar mistakes, excellent vocabulary."},
                    {"rating": "Good", "score": 4, "description": "Few grammar mistakes, good vocabulary."},
                    {"rating": "Satisfactory", "score": 3, "description": "Understandable but with errors."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Many errors, lacks clarity."},
                    {"rating": "Poor", "score": 1, "description": "Poor language, difficult to understand."}
                ]
            },
            "Bloom's Taxonomy": {
                "Remember (Knowledge)": [
                    {"rating": "Excellent", "score": 5, "description": "Accurately recalls facts, terms, and basic concepts without errors."},
                    {"rating": "Good", "score": 4, "description": "Recalls most facts and concepts with minor gaps."},
                    {"rating": "Satisfactory", "score": 3, "description": "Recalls basic information but misses some details."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Struggles to recall basic facts and concepts."},
                    {"rating": "Poor", "score": 1, "description": "Unable to recall relevant information."}
                ],
                "Understand (Comprehension)": [
                    {"rating": "Excellent", "score": 5, "description": "Clearly explains ideas and concepts in own words with examples."},
                    {"rating": "Good", "score": 4, "description": "Explains concepts well with minor clarification needed."},
                    {"rating": "Satisfactory", "score": 3, "description": "Shows basic understanding but explanation lacks depth."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Struggles to explain concepts clearly."},
                    {"rating": "Poor", "score": 1, "description": "Cannot explain or interpret the information."}
                ],
                "Apply (Application)": [
                    {"rating": "Excellent", "score": 5, "description": "Skillfully applies knowledge to new situations and solves problems."},
                    {"rating": "Good", "score": 4, "description": "Applies concepts correctly with minor errors."},
                    {"rating": "Satisfactory", "score": 3, "description": "Can apply knowledge in familiar situations only."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Struggles to apply concepts to new situations."},
                    {"rating": "Poor", "score": 1, "description": "Cannot apply knowledge appropriately."}
                ],
                "Analyze (Analysis)": [
                    {"rating": "Excellent", "score": 5, "description": "Draws insightful connections, identifies patterns, and distinguishes components."},
                    {"rating": "Good", "score": 4, "description": "Analyzes information well with good connections."},
                    {"rating": "Satisfactory", "score": 3, "description": "Shows basic analysis but misses deeper connections."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Limited analytical thinking, superficial connections."},
                    {"rating": "Poor", "score": 1, "description": "Cannot break down or analyze information."}
                ],
                "Evaluate (Evaluation)": [
                    {"rating": "Excellent", "score": 5, "description": "Makes well-reasoned judgments with strong evidence and justification."},
                    {"rating": "Good", "score": 4, "description": "Evaluates with good reasoning and some evidence."},
                    {"rating": "Satisfactory", "score": 3, "description": "Makes basic judgments but lacks strong justification."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Weak evaluation with little supporting evidence."},
                    {"rating": "Poor", "score": 1, "description": "Cannot make or justify judgments."}
                ],
                "Create (Synthesis)": [
                    {"rating": "Excellent", "score": 5, "description": "Produces original, creative work that synthesizes multiple ideas."},
                    {"rating": "Good", "score": 4, "description": "Creates new work with good originality."},
                    {"rating": "Satisfactory", "score": 3, "description": "Produces basic new work with limited creativity."},
                    {"rating": "Needs Improvement", "score": 2, "description": "Struggles to create original work."},
                    {"rating": "Poor", "score": 1, "description": "Cannot produce new or original work."}
                ]
            }
        }.get(self.level, {})

class RubricCriteria(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    level = db.Column(db.String(50))
    category = db.Column(db.String(150))
    rating = db.Column(db.String(150))
    score = db.Column(db.Integer)
    description = db.Column(db.Text)

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(150))
    student_email = db.Column(db.String(150))
    student_answer = db.Column(db.Text)
    ai_feedback = db.Column(db.Text)
    grade = db.Column(db.Float)
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id', name='fk_submission_assignment'))
    student_id = db.Column(db.Integer, db.ForeignKey('user.id', name='fk_submission_user'))
    submission_data = db.Column(db.Text)  # Add this if not already present
    
    # Helper method to get parsed submission data
    def get_submission_data(self):
        if self.submission_data:
            try:
                return json.loads(self.submission_data)
            except:
                return None
        return None
    
class GradingJob(db.Model):
    """
    Model to track status and progress of background grading jobs.
    """
    __tablename__ = 'grading_jobs'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID format
    assignment_id = db.Column(db.Integer, db.ForeignKey('assignment.id'), nullable=False)  # Changed from 'assignments.id' to 'assignment.id'
    
    # Link to Assignment model
    assignment = db.relationship('Assignment', backref=db.backref('grading_jobs', lazy=True))
    
    # Job status tracking
    status = db.Column(db.String(20), default='queued')  # queued, processing, completed, failed
    total_submissions = db.Column(db.Integer, default=0)
    processed_submissions = db.Column(db.Integer, default=0)
    
    # Results and error data
    results = db.Column(db.Text)  # JSON string containing results
    error_message = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    #assignment_ref = db.relationship('Assignment', backref=db.backref('grading_jobs', lazy=True))
    
    def __init__(self, assignment_id, job_id=None, status='queued', processed_submissions=0, total_submissions=0):
        """Initialize a new grading job."""
        import uuid
        self.id = job_id or str(uuid.uuid4())
        self.assignment_id = assignment_id
        self.status = status
        self.total_submissions = total_submissions
        self.processed_submissions = processed_submissions
    
    def to_dict(self):
        """Convert job to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'assignment_id': self.assignment_id,
            'status': self.status,
            'total_submissions': self.total_submissions,
            'processed_submissions': self.processed_submissions,
            'progress': round((self.processed_submissions / self.total_submissions * 100), 1) if self.total_submissions > 0 else 0,
            'results': json.loads(self.results) if self.results else None,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'complete': self.status in ['completed', 'failed']
        }
    
    def update_progress(self, processed_count, commit=True):
        """Update the job progress."""
        self.processed_submissions = processed_count
        self.updated_at = datetime.utcnow()
        
        if self.processed_submissions >= self.total_submissions:
            self.status = 'completed'
        
        if commit:
            db.session.commit()
    
    def complete(self, results_data, commit=True):
        """Mark job as completed with results."""
        self.status = 'completed'
        self.processed_submissions = self.total_submissions
        self.results = results_data if isinstance(results_data, str) else json.dumps(results_data)
        self.updated_at = datetime.utcnow()
        
        if commit:
            db.session.commit()
    
    def fail(self, error_message, commit=True):
        """Mark job as failed with error message."""
        self.status = 'failed'
        self.error_message = error_message
        self.updated_at = datetime.utcnow()
        
        if commit:
            db.session.commit()
# Add security utility function
def check_resource_access(resource, redirect_endpoint='views.dashboard'):
    """
    Check if the current user has access to the requested resource.
    
    Args:
        resource: The resource (Class, Rubric, etc.) to check access for
        redirect_endpoint: The endpoint to redirect to if access is denied
        
    Returns:
        Boolean: True if access is allowed, False if not
    """
    # Resource doesn't exist
    if not resource:
        return False
    
    # Admin always has access
    if hasattr(current_user, 'is_admin') and current_user.is_admin:
        return True
    
    # Check for various resource types
    if hasattr(resource, 'owner_id'):
        return resource.owner_id == current_user.id
    elif hasattr(resource, 'user_id'):
        return resource.user_id == current_user.id
    elif hasattr(resource, 'creator_id'):
        return resource.creator_id == current_user.id
    
    # For resources without direct ownership, check related resources
    if hasattr(resource, 'class_ref'):
        return check_resource_access(resource.class_ref)
    elif hasattr(resource, 'assignment_ref'):
        return check_resource_access(resource.assignment_ref)
    
    # Default to no access if no ownership relation found
    return False

def access_required(f):
    """
    Decorator to check if user has access to a resource.
    
    Usage:
    @views.route('/some-route/<int:resource_id>')
    @login_required
    @access_required
    def some_view(resource_id):
        # Get resource
        resource = Resource.query.get_or_404(resource_id)
        # View logic...
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Extract the resource ID from the URL parameters
        resource_id = None
        for param in kwargs:
            if param.endswith('_id'):
                resource_id = kwargs[param]
                resource_type = param.replace('_id', '')
                break
        
        if resource_id is None:
            flash("Resource not found", "error")
            return redirect(url_for('views.dashboard'))
        
        # Determine the model class based on the parameter name
        model_map = {
            'class': Class,
            'assignment': Assignment,
            'submission': Submission,
            'rubric': Rubric,
            'google_class': GoogleClass
        }
        
        if resource_type not in model_map:
            flash("Invalid resource type", "error")
            return redirect(url_for('views.dashboard'))
        
        # Get the resource
        resource = model_map[resource_type].query.get_or_404(resource_id)
        
        # Check access
        if not check_resource_access(resource):
            flash("You do not have permission to access this resource", "error")
            return redirect(url_for('views.dashboard'))
        
        return f(*args, **kwargs)
    
    return decorated_function
