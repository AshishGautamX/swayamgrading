# website/extensions.py
"""
Flask extensions initialization.
All extensions are initialized here and then bound to the app in create_app().
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from authlib.integrations.flask_client import OAuth

import logging

logger = logging.getLogger(__name__)

# Core extensions
db = SQLAlchemy()
login_manager = LoginManager()
oauth = OAuth()
csrf = CSRFProtect()
migrate = Migrate()

# Optional extensions - initialized lazily
_cache = None
_limiter = None
_celery = None


def get_cache():
    """Get Flask-Caching instance, creating if needed."""
    global _cache
    if _cache is None:
        try:
            from flask_caching import Cache
            _cache = Cache()
        except ImportError:
            logger.warning("Flask-Caching not installed. Caching disabled.")
    return _cache


def get_limiter():
    """Get Flask-Limiter instance, creating if needed."""
    global _limiter
    if _limiter is None:
        try:
            from flask_limiter import Limiter
            from flask_limiter.util import get_remote_address
            _limiter = Limiter(key_func=get_remote_address)
        except ImportError:
            logger.warning("Flask-Limiter not installed. Rate limiting disabled.")
    return _limiter


def init_extensions(app):
    """Initialize all extensions with the Flask app."""
    
    # Core extensions
    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    
    # Configure login manager
    login_manager.login_view = 'auth.google_login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    
    # Optional: Flask-Caching
    cache = get_cache()
    if cache:
        cache_config = {
            'CACHE_TYPE': app.config.get('CACHE_TYPE', 'SimpleCache'),
            'CACHE_DEFAULT_TIMEOUT': app.config.get('CACHE_DEFAULT_TIMEOUT', 300),
        }
        if app.config.get('CACHE_TYPE') == 'RedisCache':
            cache_config['CACHE_REDIS_URL'] = app.config.get('CACHE_REDIS_URL')
        
        cache.init_app(app, config=cache_config)
        app.cache = cache
        logger.info(f"Caching initialized with type: {cache_config['CACHE_TYPE']}")
    
    # Optional: Flask-Limiter
    limiter = get_limiter()
    if limiter:
        storage_url = app.config.get('RATELIMIT_STORAGE_URL', 'memory://')
        limiter._storage_uri = storage_url
        limiter.init_app(app)
        app.limiter = limiter
        logger.info(f"Rate limiting initialized with storage: {storage_url}")
    
    return app
