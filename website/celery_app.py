# website/celery_app.py
"""
Celery application configuration for background tasks.
"""

import os
from celery import Celery


def make_celery(app=None):
    """
    Create and configure Celery application.
    
    Args:
        app: Flask application instance (optional)
        
    Returns:
        Configured Celery application
    """
    celery = Celery(
        'aigrader',
        broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        backend=os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
        include=['website.tasks']
    )
    
    # Celery configuration
    celery.conf.update(
        # Task settings
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        
        # Performance settings
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        
        # Result settings
        result_expires=3600,  # Results expire after 1 hour
        
        # Rate limiting
        task_annotations={
            'website.tasks.grade_submission_task': {'rate_limit': '10/m'},
            'website.tasks.grade_all_task': {'rate_limit': '2/m'},
        },
        
        # Retry settings
        task_default_retry_delay=60,  # 1 minute
        task_max_retries=3,
    )
    
    if app:
        celery.conf.update(app.config)
        
        class ContextTask(celery.Task):
            """Task class that runs within Flask app context."""
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)
        
        celery.Task = ContextTask
    
    return celery


# Create default Celery instance
celery = make_celery()
