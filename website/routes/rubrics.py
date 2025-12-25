# website/routes/rubrics.py
"""
Rubric routes for the AIGrader application.
Handles rubric management.
"""

import json
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from . import views
from ..models import Rubric, db


@views.route('/create-rubric', methods=['GET', 'POST'])
@login_required
def create_rubric():
    """Create a new rubric."""
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        level = request.form.get('level')
        
        if not name or not level:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': 'Name and level are required'})
            flash('Name and level are required!', category='error')
            return redirect(url_for('views.create_rubric'))
        
        try:
            new_rubric = Rubric(
                name=name,
                description=description or '',
                level=level,
                criteria=json.dumps([]),  # Criteria will be generated dynamically
                creator_id=current_user.id
            )
            db.session.add(new_rubric)
            db.session.commit()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': 'Rubric created successfully'})
            
            flash('Rubric created successfully!', category='success')
            return redirect(url_for('views.view_rubrics'))
            
        except Exception as e:
            db.session.rollback()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': str(e)})
            flash('Error creating rubric: ' + str(e), category='error')
            return redirect(url_for('views.create_rubric'))
    
    # GET request - render form
    return render_template('rubric_form.html')


@views.route('/rubrics')
@login_required
def view_rubrics():
    """View all rubrics available to the user."""
    # Get user-created and system rubrics
    rubrics = Rubric.query.filter(
        (Rubric.creator_id == current_user.id) | (Rubric.creator_id == None)
    ).all()
    
    return render_template('rubrics.html', rubrics=rubrics, user=current_user)
