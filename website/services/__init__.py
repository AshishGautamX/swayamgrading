# website/services/__init__.py
"""
Services layer for the AIGrader application.
Contains business logic separated from routes.
"""

from .ai_grading import AIGradingService
from .file_processing import FileProcessingService

__all__ = [
    'AIGradingService',
    'FileProcessingService'
]
