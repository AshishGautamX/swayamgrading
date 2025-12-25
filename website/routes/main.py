# website/routes/main.py
"""
Main routes for the AIGrader application.
Handles home page and dashboard.
"""

from flask import render_template, redirect, url_for
from flask_login import login_required, current_user

from . import views
from ..models import Rubric


@views.route('/')
def home():
    """
    Homepage route.
    Redirects to dashboard if user is authenticated, otherwise shows landing page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('views.dashboard'))
    return render_template('home.html')


@views.route('/dashboard')
@login_required
def dashboard():
    """
    User dashboard showing classes and rubrics.
    """
    # Get both user-created rubrics and system-created default rubrics (limit to 3 for preview)
    rubrics = Rubric.query.filter(
        (Rubric.creator_id == current_user.id) | (Rubric.creator_id == None)
    ).limit(3).all()
    
    return render_template('dashboard.html', 
                         user=current_user, 
                         classes=current_user.classes,
                         rubrics=rubrics)
