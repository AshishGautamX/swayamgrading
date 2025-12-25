# website/routes/classroom.py
"""
Classroom routes for the AIGrader application.
Handles class and assignment management.
"""

from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from . import views
from ..models import Class, Assignment, Submission, Rubric, db, check_resource_access
from ..utils.validators import validate_class_name, validate_text_field


@views.route('/create-class', methods=['GET', 'POST'])
@login_required
def create_class():
    """Create a new class with an initial assignment."""
    if request.method == 'POST':
        try:
            # Get form data
            class_name = request.form.get('class_name')
            assignment_name = request.form.get('assignment_name')
            question = request.form.get('question')
            level = request.form.get('level')
            rubric_id = request.form.get('rubric_id')
            
            # Validate required fields
            if not class_name or not assignment_name or not question or not level or not rubric_id:
                flash('All fields are required!', category='error')
                return redirect(url_for('views.create_class'))

            # Create new class
            new_class = Class(
                name=class_name,
                level=level,
                owner_id=current_user.id
            )
            db.session.add(new_class)
            db.session.commit()

            # Create default assignment
            new_assignment = Assignment(
                name=assignment_name,
                question=question,
                rubric_id=rubric_id,
                class_id=new_class.id
            )
            db.session.add(new_assignment)
            db.session.commit()

            flash('Class created successfully!', category='success')
            return redirect(url_for('views.view_class', class_id=new_class.id))

        except Exception as e:
            db.session.rollback()
            flash('Error creating class: ' + str(e), category='error')
            return redirect(url_for('views.create_class'))

    # If GET request, fetch rubrics and render the form
    rubrics = Rubric.query.all()
    return render_template('create_class.html', user=current_user, form={}, rubrics=rubrics)


@views.route('/class/<int:class_id>')
@login_required
def view_class(class_id):
    """View a specific class with its assignments."""
    cls = Class.query.options(
        db.joinedload(Class.assignments).joinedload(Assignment.submissions)
    ).get_or_404(class_id)
    
    # Security: Check if user owns this class
    if not check_resource_access(cls):
        flash('You do not have permission to view this class!', category='error')
        return redirect(url_for('views.dashboard'))
    
    return render_template("class.html", user=current_user, cls=cls, assignments=cls.assignments)


@views.route('/delete-class/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    """Delete a class and all its assignments and submissions."""
    try:
        # Fetch the class
        cls = Class.query.get_or_404(class_id)
        
        # Check if the current user is the owner of the class
        if cls.owner_id != current_user.id:
            flash('You do not have permission to delete this class!', category='error')
            return redirect(url_for('views.dashboard'))
            
        # Delete associated assignments and their submissions
        for assignment in cls.assignments:
            # Delete all submissions for this assignment
            Submission.query.filter_by(assignment_id=assignment.id).delete()
            
        # Delete all assignments for this class
        Assignment.query.filter_by(class_id=class_id).delete()
            
        # Delete the class
        db.session.delete(cls)
        db.session.commit()
        
        flash('Class deleted successfully!', category='success')
        return redirect(url_for('views.dashboard'))
        
    except Exception as e:
        db.session.rollback()
        flash('Error deleting class: ' + str(e), category='error')
        return redirect(url_for('views.dashboard'))


@views.route('/create-assignment/<int:class_id>', methods=['GET', 'POST'])
@login_required
def create_assignment(class_id):
    """Create a new assignment for a class."""
    cls = Class.query.get_or_404(class_id)
    
    # Security: Check if user owns this class
    if not check_resource_access(cls):
        flash('You do not have permission to create assignments for this class!', category='error')
        return redirect(url_for('views.dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        question = request.form.get('question')
        rubric_id = request.form.get('rubric_id')
        
        # Input validation
        valid, result = validate_text_field(name, 'Assignment name', max_length=150)
        if not valid:
            flash(result, category='error')
            return redirect(url_for('views.create_assignment', class_id=class_id))
        name = result
        
        valid, result = validate_text_field(question, 'Question')
        if not valid:
            flash(result, category='error')
            return redirect(url_for('views.create_assignment', class_id=class_id))
        question = result
        
        # Create new assignment
        new_assignment = Assignment(
            name=name,
            question=question,
            rubric_id=rubric_id,
            class_id=class_id
        )
        
        db.session.add(new_assignment)
        db.session.commit()
        
        flash('Assignment created successfully!', category='success')
        return redirect(url_for('views.view_class', class_id=class_id))
    
    # If GET request, render the form with rubrics
    rubrics = Rubric.query.filter(
        (Rubric.creator_id == current_user.id) | (Rubric.creator_id == None)
    ).all()
    return render_template('create_assignment.html', cls=cls, rubrics=rubrics)


@views.route('/delete-assignment/<int:assignment_id>', methods=['POST'])
@login_required
def delete_assignment(assignment_id):
    """Delete an assignment and all its submissions."""
    assignment = Assignment.query.get_or_404(assignment_id)
    class_id = assignment.class_id
    
    # Security check
    if not check_resource_access(assignment.class_ref):
        flash('You do not have permission to delete this assignment!', category='error')
        return redirect(url_for('views.dashboard'))
    
    try:
        # Delete all submissions for this assignment
        Submission.query.filter_by(assignment_id=assignment_id).delete()
        
        # Delete the assignment
        db.session.delete(assignment)
        db.session.commit()
        
        flash('Assignment deleted successfully!', category='success')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting assignment: ' + str(e), category='error')
    
    return redirect(url_for('views.view_class', class_id=class_id))
