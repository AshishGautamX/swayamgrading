# website/utils/validators.py
"""
Input validation utilities for the AIGrader application.
Provides functions to sanitize and validate user inputs.
"""

import re
import html


def sanitize_input(text, max_length=10000):
    """
    Sanitize user input to prevent XSS and limit length.
    
    Args:
        text: The input text to sanitize
        max_length: Maximum allowed length (default 10000)
        
    Returns:
        Sanitized string or None if input was None
    """
    if text is None:
        return None
    # Convert to string and strip
    text = str(text).strip()
    # Limit length
    if len(text) > max_length:
        text = text[:max_length]
    # HTML escape to prevent XSS
    return html.escape(text)


def validate_class_name(name):
    """
    Validate class name.
    
    Args:
        name: The class name to validate
        
    Returns:
        Tuple of (is_valid: bool, result: str)
        If valid, result is the sanitized name
        If invalid, result is the error message
    """
    if not name or len(name.strip()) < 1:
        return False, "Class name is required"
    if len(name) > 150:
        return False, "Class name must be less than 150 characters"
    return True, sanitize_input(name)


def validate_email(email):
    """
    Validate email format.
    
    Args:
        email: The email address to validate
        
    Returns:
        Tuple of (is_valid: bool, result: str)
        If valid, result is the normalized email
        If invalid, result is the error message
    """
    if not email:
        return False, "Email is required"
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False, "Invalid email format"
    if len(email) > 150:
        return False, "Email must be less than 150 characters"
    return True, email.lower().strip()


def validate_text_field(text, field_name, max_length=10000, required=True):
    """
    Validate a generic text field.
    
    Args:
        text: The text to validate
        field_name: Name of the field (for error messages)
        max_length: Maximum allowed length
        required: Whether the field is required
        
    Returns:
        Tuple of (is_valid: bool, result: str)
        If valid, result is the sanitized text
        If invalid, result is the error message
    """
    if required and (not text or len(text.strip()) < 1):
        return False, f"{field_name} is required"
    if text and len(text) > max_length:
        return False, f"{field_name} must be less than {max_length} characters"
    return True, sanitize_input(text) if text else None


def validate_rubric_id(rubric_id):
    """
    Validate rubric ID.
    
    Args:
        rubric_id: The rubric ID to validate
        
    Returns:
        Tuple of (is_valid: bool, result: int or str)
        If valid, result is the integer rubric ID
        If invalid, result is the error message
    """
    if not rubric_id:
        return False, "Rubric ID is required"
    try:
        return True, int(rubric_id)
    except (ValueError, TypeError):
        return False, "Invalid rubric ID format"
