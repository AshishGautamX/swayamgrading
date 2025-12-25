# website/services/ai_grading.py
"""
AI Grading Service for the AIGrader application.
Handles all AI-related grading functionality.
"""

import os
import json
import logging
from huggingface_hub import InferenceClient
from ..utils.helpers import clean_ai_response, extract_grade, parse_ai_score

logger = logging.getLogger(__name__)

# Configuration
API_KEY = os.getenv("HUGGINGFACE_API_KEY")
MODEL_NAME = os.getenv("AI_MODEL_NAME", "meta-llama/Llama-3.3-70B-Instruct")


class AIGradingService:
    """Service class for AI-powered grading functionality."""
    
    def __init__(self):
        """Initialize the AI grading service."""
        self.client = InferenceClient(
            token=API_KEY, 
            base_url="https://router.huggingface.co"
        )
        self.model_name = MODEL_NAME
    
    def build_grading_prompt(self, question, student_answer, rubric_criteria, school_level="High School"):
        """
        Build a prompt for AI grading.
        
        Args:
            question: The assignment question
            student_answer: The student's answer
            rubric_criteria: List of rubric criteria dictionaries
            school_level: The school level for age-appropriate feedback
            
        Returns:
            Formatted prompt string
        """
        criteria_text = ""
        if rubric_criteria:
            for criterion in rubric_criteria:
                criteria_text += f"\n- {criterion.get('name', 'Unknown')}: {criterion.get('description', 'No description')}"
        
        prompt = f"""You are an expert teacher grading student work. Evaluate the following student response based on the rubric criteria provided.

**Question/Assignment:**
{question}

**Student Answer:**
{student_answer}

**Rubric Criteria:**
{criteria_text if criteria_text else "General assessment of content, clarity, and accuracy"}

**School Level:** {school_level}

Please provide your evaluation in the following JSON format:
{{
    "grade": "<score>/100",
    "feedback": "<detailed constructive feedback>",
    "glow": "<what the student did well>",
    "grow": "<areas for improvement>",
    "summary": "<brief 1-2 sentence summary>"
}}

Be age-appropriate, constructive, and specific in your feedback. Focus on helping the student improve."""
        
        return prompt
    
    def grade_submission(self, question, student_answer, rubric_criteria=None, school_level="High School"):
        """
        Grade a single submission using AI.
        
        Args:
            question: The assignment question
            student_answer: The student's answer
            rubric_criteria: Optional list of rubric criteria
            school_level: The school level for context
            
        Returns:
            Dictionary with grading results
        """
        try:
            prompt = self.build_grading_prompt(question, student_answer, rubric_criteria, school_level)
            
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.7
            )
            
            response_text = response.choices[0].message.content
            cleaned_response = clean_ai_response(response_text)
            
            try:
                result = json.loads(cleaned_response)
            except json.JSONDecodeError:
                # Fallback parsing
                result = {
                    "grade": extract_grade(response_text) or "70/100",
                    "feedback": response_text,
                    "glow": "Good effort on this assignment.",
                    "grow": "Continue developing your ideas.",
                    "summary": "Submission evaluated."
                }
            
            # Ensure grade is properly formatted
            if 'grade' in result and not isinstance(result['grade'], str):
                result['grade'] = f"{result['grade']}/100"
            
            return result
            
        except Exception as e:
            logger.error(f"Error in AI grading: {str(e)}")
            return {
                "grade": "Error",
                "feedback": f"Unable to grade submission: {str(e)}",
                "glow": "",
                "grow": "",
                "summary": "Grading failed due to an error."
            }
    
    def evaluate_with_rubric(self, question, answer, criteria, school_level):
        """
        Generate AI evaluation using specific rubric criteria.
        
        Args:
            question: The question/assignment
            answer: Student's answer
            criteria: Specific criteria to evaluate
            school_level: School level context
            
        Returns:
            AI response text
        """
        prompt = f"""Evaluate this student response for the criterion: "{criteria}"

Question: {question}
Student Answer: {answer}
School Level: {school_level}

Provide a score out of 100 and brief explanation."""

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.5
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error in rubric evaluation: {str(e)}")
            return f"Error evaluating: {str(e)}"


# Singleton instance for easy access
_ai_grading_service = None


def get_ai_grading_service():
    """Get the singleton AI grading service instance."""
    global _ai_grading_service
    if _ai_grading_service is None:
        _ai_grading_service = AIGradingService()
    return _ai_grading_service
