# website/services/file_processing.py
"""
File Processing Service for the AIGrader application.
Handles PDF text extraction and file processing.
"""

import os
import io
import logging
import tempfile

logger = logging.getLogger(__name__)


class FileProcessingService:
    """Service class for file processing functionality."""
    
    @staticmethod
    def extract_pdf_text(file_content):
        """
        Extract text from PDF file content.
        
        Args:
            file_content: The PDF file bytes or file-like object
            
        Returns:
            Tuple of (success: bool, result: str)
            If success, result is the extracted text
            If failure, result is the error message
        """
        try:
            from PyPDF2 import PdfReader
            
            if isinstance(file_content, bytes):
                file_like = io.BytesIO(file_content)
            else:
                file_like = file_content
            
            pdf_reader = PdfReader(file_like)
            extracted_text = ""
            
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    extracted_text += page_text + "\n"
            
            if not extracted_text.strip():
                return False, "Could not extract text from PDF. The PDF may be image-based."
            
            return True, extracted_text.strip()
            
        except Exception as e:
            logger.error(f"Error extracting PDF text: {str(e)}")
            return False, f"Error processing PDF: {str(e)}"
    
    @staticmethod
    def extract_docx_text(file_content):
        """
        Extract text from DOCX file content.
        
        Args:
            file_content: The DOCX file bytes
            
        Returns:
            Tuple of (success: bool, result: str)
        """
        try:
            import docx
            
            if isinstance(file_content, bytes):
                file_like = io.BytesIO(file_content)
            else:
                file_like = file_content
            
            doc = docx.Document(file_like)
            extracted_text = "\n".join([para.text for para in doc.paragraphs])
            
            if not extracted_text.strip():
                return False, "Could not extract text from document."
            
            return True, extracted_text.strip()
            
        except Exception as e:
            logger.error(f"Error extracting DOCX text: {str(e)}")
            return False, f"Error processing document: {str(e)}"
    
    @staticmethod
    def extract_text_from_file(file_content, mime_type):
        """
        Extract text from a file based on its MIME type.
        
        Args:
            file_content: The file bytes
            mime_type: The MIME type of the file
            
        Returns:
            Tuple of (success: bool, result: str)
        """
        if mime_type == 'application/pdf':
            return FileProcessingService.extract_pdf_text(file_content)
        elif mime_type in ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                          'application/msword']:
            return FileProcessingService.extract_docx_text(file_content)
        elif mime_type.startswith('text/'):
            try:
                text = file_content.decode('utf-8', errors='ignore')
                return True, text
            except Exception as e:
                return False, f"Error reading text file: {str(e)}"
        else:
            return False, f"Unsupported file type: {mime_type}"
    
    @staticmethod
    def save_temp_file(file_content, suffix=".tmp"):
        """
        Save file content to a temporary file.
        
        Args:
            file_content: The file bytes
            suffix: File extension suffix
            
        Returns:
            Path to the temporary file
        """
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(file_content)
            return tmp.name
    
    @staticmethod
    def cleanup_temp_file(file_path):
        """
        Clean up a temporary file.
        
        Args:
            file_path: Path to the file to delete
        """
        try:
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.warning(f"Failed to cleanup temp file {file_path}: {e}")


# Singleton instance
_file_processing_service = None


def get_file_processing_service():
    """Get the singleton file processing service instance."""
    global _file_processing_service
    if _file_processing_service is None:
        _file_processing_service = FileProcessingService()
    return _file_processing_service
