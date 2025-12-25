import os
import logging
from flask import Flask
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import extensions from the extensions module
from .extensions import db, login_manager, oauth, csrf, migrate, init_extensions


def create_app(config_name=None):
    """
    Application factory for creating Flask application instances.
    
    Args:
        config_name: Configuration name ('development', 'production', 'testing')
                    If None, uses FLASK_ENV environment variable
    
    Returns:
        Flask application instance
    """
    app = Flask(__name__)
    
    # Load configuration
    from .config import get_config, config
    if config_name:
        app.config.from_object(config.get(config_name, config['default']))
    else:
        app.config.from_object(get_config())
    
    # Override with environment variables if present
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', app.config.get('SECRET_KEY'))
    # Check SQLALCHEMY_DATABASE_URI first (from .env), then DATABASE_URL (for Heroku/etc)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 
                                                       os.getenv('DATABASE_URL', 
                                                                 app.config.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///database.db')))
    app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
    
    # Pagination settings
    app.config['ITEMS_PER_PAGE'] = int(os.getenv('ITEMS_PER_PAGE', 20))
    app.config['MAX_ITEMS_PER_PAGE'] = int(os.getenv('MAX_ITEMS_PER_PAGE', 100))
    
    # Initialize all extensions
    init_extensions(app)
    
    # User loader for Flask-Login
    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Register blueprints
    from .auth import auth
    
    # Try to import from new modular routes, fallback to old views
    try:
        from .routes import views
    except ImportError:
        from .views import views

    app.register_blueprint(auth)
    app.register_blueprint(views)

    # Database initialization and default data
    with app.app_context():
        db.create_all()
        
        # Create default Bloom's Taxonomy rubric if it doesn't exist
        from .models import Rubric
        blooms_rubric = Rubric.query.filter_by(name="Bloom's Taxonomy (Default)", level="Bloom's Taxonomy").first()
        if not blooms_rubric:
            default_rubric = Rubric(
                name="Bloom's Taxonomy (Default)",
                description="Default rubric based on Bloom's Taxonomy cognitive levels",
                level="Bloom's Taxonomy",
                criteria=json.dumps([]),
                creator_id=None
            )
            db.session.add(default_rubric)
            db.session.commit()
            logger.info("Created default Bloom's Taxonomy rubric")

    # Template filters
    @app.template_filter('to_json')
    def to_json(value):
        return json.dumps(value)

    @app.template_filter('from_json')
    def from_json(value):
        return json.loads(value)
    
    # Health check endpoints
    @app.route('/health')
    def health_check():
        """Basic health check endpoint."""
        return {'status': 'healthy', 'version': '1.0.0'}, 200
    
    @app.route('/ready')
    def readiness_check():
        """Readiness check with database connectivity test."""
        try:
            db.session.execute(db.text('SELECT 1'))
            
            # Check cache if available
            cache_status = 'not configured'
            if hasattr(app, 'cache'):
                try:
                    app.cache.set('health_check', 'ok', timeout=10)
                    if app.cache.get('health_check') == 'ok':
                        cache_status = 'connected'
                except:
                    cache_status = 'error'
            
            return {
                'status': 'ready', 
                'database': 'connected',
                'cache': cache_status
            }, 200
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return {'status': 'not ready', 'error': str(e)}, 503

    return app
