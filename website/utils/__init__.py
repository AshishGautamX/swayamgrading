# website/utils/__init__.py
"""
Utility functions and helpers for the AIGrader application.
"""

from .validators import (
    sanitize_input,
    validate_class_name,
    validate_email,
    validate_text_field
)

from .helpers import (
    extract_grade,
    clean_ai_response,
    extract_section,
    parse_ai_score
)

__all__ = [
    'sanitize_input',
    'validate_class_name',
    'validate_email',
    'validate_text_field',
    'extract_grade',
    'clean_ai_response',
    'extract_section',
    'parse_ai_score'
]
