# website/routes/__init__.py
"""
Routes package for the AIGrader application.
Contains separate blueprints for different feature areas.
"""

from flask import Blueprint

# Create main blueprint that will hold all route modules
# We'll keep using 'views' as the blueprint name for backward compatibility
views = Blueprint('views', __name__)

# Import route modules to register them with the blueprint
from . import main
from . import classroom
from . import grading
from . import submissions
from . import rubrics
from . import google_integration

__all__ = ['views']
