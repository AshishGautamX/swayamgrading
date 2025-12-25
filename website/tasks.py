# website/tasks.py
"""
Celery background tasks for the AIGrader application.
"""

import logging
from .celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3)
def grade_submission_task(self, submission_id, rubric_id=None):
    """
    Background task to grade a single submission.
    
    Args:
        submission_id: ID of the submission to grade
        rubric_id: Optional rubric ID to use for grading
        
    Returns:
        Dictionary with grading results
    """
    try:
        from .models import Submission, Rubric, db
        from .services.ai_grading import get_ai_grading_service
        
        submission = Submission.query.get(submission_id)
        if not submission:
            return {'error': 'Submission not found'}
        
        assignment = submission.assignment_ref
        rubric = Rubric.query.get(rubric_id) if rubric_id else None
        
        ai_service = get_ai_grading_service()
        rubric_criteria = rubric.get_criteria() if rubric else []
        
        result = ai_service.grade_submission(
            assignment.question,
            submission.student_answer,
            rubric_criteria,
            rubric.level if rubric else "High School"
        )
        
        # Update submission
        grade_str = result.get('grade', '70/100')
        if '/' in str(grade_str):
            try:
                submission.grade = float(grade_str.split('/')[0])
            except:
                submission.grade = 70
        else:
            submission.grade = float(grade_str) if grade_str else 70
        
        submission.feedback = result.get('feedback', '')
        db.session.commit()
        
        return {
            'success': True,
            'submission_id': submission_id,
            'grade': submission.grade,
            'feedback': submission.feedback
        }
        
    except Exception as e:
        logger.error(f"Error grading submission {submission_id}: {e}")
        self.retry(exc=e, countdown=60)


@celery.task(bind=True, max_retries=2)
def grade_all_task(self, job_id, submission_ids, rubric_id=None, skip_graded=True):
    """
    Background task to grade multiple submissions.
    
    Args:
        job_id: ID of the grading job for tracking
        submission_ids: List of submission IDs to grade
        rubric_id: Optional rubric ID to use
        skip_graded: Whether to skip already graded submissions
        
    Returns:
        Dictionary with job results
    """
    try:
        from .models import Submission, Rubric, GradingJob, db
        from .services.ai_grading import get_ai_grading_service
        
        job = GradingJob.query.get(job_id)
        if not job:
            return {'error': 'Job not found'}
        
        job.status = 'processing'
        db.session.commit()
        
        rubric = Rubric.query.get(rubric_id) if rubric_id else None
        ai_service = get_ai_grading_service()
        
        for submission_id in submission_ids:
            submission = Submission.query.get(submission_id)
            if not submission:
                continue
            
            # Skip if already graded
            if skip_graded and submission.grade is not None and submission.feedback:
                job.processed_count += 1
                job.current_message = f"Skipped {submission.student_name} (already graded)"
                db.session.commit()
                continue
            
            job.current_message = f"Grading {submission.student_name}..."
            db.session.commit()
            
            assignment = submission.assignment_ref
            rubric_criteria = rubric.get_criteria() if rubric else []
            
            try:
                result = ai_service.grade_submission(
                    assignment.question,
                    submission.student_answer,
                    rubric_criteria,
                    rubric.level if rubric else "High School"
                )
                
                # Update submission
                grade_str = result.get('grade', '70/100')
                if '/' in str(grade_str):
                    try:
                        submission.grade = float(grade_str.split('/')[0])
                    except:
                        submission.grade = 70
                else:
                    submission.grade = float(grade_str) if grade_str else 70
                
                submission.feedback = result.get('feedback', '')
                
            except Exception as e:
                logger.error(f"Error grading submission {submission_id}: {e}")
                submission.feedback = f"Error: {str(e)}"
            
            job.processed_count += 1
            db.session.commit()
        
        job.status = 'completed'
        job.current_message = 'All submissions graded'
        db.session.commit()
        
        return {
            'success': True,
            'job_id': job_id,
            'processed_count': job.processed_count
        }
        
    except Exception as e:
        logger.error(f"Error in batch grading job {job_id}: {e}")
        if job:
            job.status = 'error'
            job.error_message = str(e)
            db.session.commit()
        self.retry(exc=e, countdown=120)


@celery.task
def cleanup_old_jobs():
    """
    Periodic task to clean up old grading jobs.
    Should be scheduled to run daily.
    """
    from datetime import datetime, timedelta
    from .models import GradingJob, db
    
    # Delete jobs older than 7 days
    cutoff = datetime.utcnow() - timedelta(days=7)
    old_jobs = GradingJob.query.filter(GradingJob.created_at < cutoff).all()
    
    count = len(old_jobs)
    for job in old_jobs:
        db.session.delete(job)
    
    db.session.commit()
    logger.info(f"Cleaned up {count} old grading jobs")
    
    return {'deleted_count': count}
