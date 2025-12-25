# website/utils/helpers.py
"""
Helper functions for the AIGrader application.
Provides utility functions for text processing, grade extraction, and AI response parsing.
"""

import re
import json
import logging

logger = logging.getLogger(__name__)


def extract_grade(text):
    """
    Extract numerical grade from text.
    Looks for patterns like "65/100" or "grade: 75" and returns the numerical value.
    
    Args:
        text: The text to extract grade from
        
    Returns:
        Float grade value or None if not found
    """
    if not text:
        return None
    
    # Look for specific patterns like "65/100"
    grade_pattern = re.search(r'(\d+)\/100', text)
    if grade_pattern:
        grade = float(grade_pattern.group(1))
        return grade
    
    # Look for "grade: 75" or similar patterns
    grade_key_pattern = re.search(r'grade[\s:]+([\d.]+)', text, re.IGNORECASE)
    if grade_key_pattern:
        grade = float(grade_key_pattern.group(1))
        return grade
    
    # Look for any number between 0 and 100 that could be a grade
    number_pattern = re.search(r'\b([0-9]{1,2}|100)\b', text)
    if number_pattern:
        grade = float(number_pattern.group(1))
        return grade
    
    return None


def clean_ai_response(text):
    """
    Clean the AI response to extract valid JSON.
    Removes markdown code blocks, backticks, and other non-JSON content.
    
    Args:
        text: The AI response text to clean
        
    Returns:
        A valid JSON string
    """
    if not text:
        return "{}"
    
    # Remove markdown code blocks and backticks
    cleaned_text = re.sub(r'```json\s*|\s*```|`', '', text.strip())
    
    # Try to extract a JSON object if there's text before or after the JSON
    json_pattern = re.compile(r'(\{.*\})', re.DOTALL)
    match = json_pattern.search(cleaned_text)
    if match:
        potential_json = match.group(1)
        # Verify it's valid JSON with a quick test before returning
        try:
            json.loads(potential_json)
            return potential_json
        except json.JSONDecodeError:
            pass
    
    # Check if the cleaned text itself might be valid JSON
    try:
        json.loads(cleaned_text)
        return cleaned_text
    except json.JSONDecodeError:
        # Try to convert it to a JSON-like structure
        try:
            result = {}
            current_key = None
            lines = cleaned_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Look for key-value patterns like "Feedback: This is feedback"
                kv_match = re.match(r'^(feedback|grade|summary|glow|grow|think_about_it|rubric):(.*)$', line, re.IGNORECASE)
                if kv_match:
                    current_key = kv_match.group(1).lower()
                    result[current_key] = kv_match.group(2).strip()
                elif current_key and line:
                    # Append to existing key
                    result[current_key] = result.get(current_key, "") + " " + line
            
            if result:
                return json.dumps(result)
        except Exception as e:
            logger.warning(f"Failed to create structured JSON: {e}")
    
    # Last resort: wrap the cleaned text in a minimal JSON structure
    return json.dumps({"feedback": cleaned_text, "grade": "70/100"})


def extract_section(text, *keywords):
    """
    Extract sections from the AI response based on keywords.
    
    Args:
        text: The text to extract from
        *keywords: Keywords to look for as section headers
        
    Returns:
        Extracted section text or default message
    """
    if not text:
        return "No information available."
    
    text_lower = text.lower()
    lines = text.split('\n')
    
    # Try to find sections with headings matching keywords
    for i, line in enumerate(lines):
        line_lower = line.lower()
        for keyword in keywords:
            if keyword.lower() in line_lower and i < len(lines) - 1:
                # Extract text until the next section or end
                section_text = []
                j = i + 1
                while j < len(lines) and not any(k.lower() in lines[j].lower() for k in 
                                               ['feedback:', 'grade:', 'summary:', 'glow:', 'grow:', 'think:', 'rubric:']):
                    if lines[j].strip():
                        section_text.append(lines[j])
                    j += 1
                if section_text:
                    result = " ".join(section_text).strip()
                    return result
    
    # Fallback: Look for sentences containing keywords
    for keyword in keywords:
        pattern = re.compile(r'[^.!?]*\b' + re.escape(keyword.lower()) + r'\b[^.!?]*[.!?]', re.IGNORECASE)
        matches = pattern.findall(text_lower)
        if matches:
            result = " ".join(matches).strip().capitalize()
            return result
    
    return "Information not explicitly provided in the feedback."


def parse_ai_score(ai_response):
    """
    Extract score from AI response text.
    
    Args:
        ai_response: The AI response text
        
    Returns:
        Integer score or None
    """
    if not ai_response:
        return None
    
    # Look for score patterns
    score_match = re.search(r'(\d+)\s*/\s*\d+', ai_response)
    if score_match:
        return int(score_match.group(1))
    
    score_match = re.search(r'score[:\s]+(\d+)', ai_response, re.IGNORECASE)
    if score_match:
        return int(score_match.group(1))
    
    return None


def format_grade_for_email(grade, max_grade=100):
    """
    Format a grade for display in an email.
    
    Args:
        grade: The numerical grade
        max_grade: Maximum possible grade (default 100)
        
    Returns:
        Formatted grade string
    """
    if grade is None:
        return "Not graded"
    return f"{grade}/{max_grade}"


def truncate_text(text, max_length=500, suffix="..."):
    """
    Truncate text to a maximum length with a suffix.
    
    Args:
        text: The text to truncate
        max_length: Maximum length before truncation
        suffix: Suffix to add after truncation
        
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
