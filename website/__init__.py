import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from authlib.integrations.flask_client import OAuth
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

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
oauth = OAuth()
csrf = CSRFProtect()

# Try to import Flask-Limiter (optional for rate limiting)
try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    # Use memory storage explicitly (for development)
    # For production, use Redis: storage_uri="redis://localhost:6379"
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"],
        storage_uri="memory://"  # Explicit memory storage
    )
    LIMITER_AVAILABLE = True
except ImportError:
    limiter = None
    LIMITER_AVAILABLE = False
    logger.warning("Flask-Limiter not installed. Rate limiting disabled.")


def create_app():
    app = Flask(__name__)
    
    # Load configuration from environment variables
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', 'sqlite:///database.db')
    app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
    
    # Security configurations
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour CSRF token validity
    app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    
    # Database pool configuration (for production with PostgreSQL)
    app.config['SQLALCHEMY_POOL_SIZE'] = int(os.getenv('DB_POOL_SIZE', 10))
    app.config['SQLALCHEMY_POOL_RECYCLE'] = 300
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)
    csrf.init_app(app)
    
    # Initialize rate limiter if available
    if LIMITER_AVAILABLE and limiter:
        limiter.init_app(app)
        app.limiter = limiter
    
    login_manager.login_view = 'auth.google_login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .auth import auth
    
    # Try to import from new modular routes, fallback to old views
    try:
        from .routes import views
    except ImportError:
        from .views import views

    # Register blueprints
    app.register_blueprint(auth)
    app.register_blueprint(views)

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
                criteria=json.dumps([]),  # Criteria are generated dynamically from get_criteria()
                creator_id=None  # System-created rubric
            )
            db.session.add(default_rubric)
            db.session.commit()
            logger.info("Created default Bloom's Taxonomy rubric")

    Migrate(app, db)

    @app.template_filter('to_json')
    def to_json(value):
        return json.dumps(value)

    @app.template_filter('from_json')
    def from_json(value):
        return json.loads(value)
    
    # Health check endpoint
    @app.route('/health')
    def health_check():
        return {'status': 'healthy', 'version': '1.0.0'}, 200
    
    @app.route('/ready')
    def readiness_check():
        try:
            # Check database connection
            db.session.execute(db.text('SELECT 1'))
            return {'status': 'ready', 'database': 'connected'}, 200
        except Exception as e:
            logger.error(f"Readiness check failed: {e}")
            return {'status': 'not ready', 'error': str(e)}, 503

    return app
