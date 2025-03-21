import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from authlib.integrations.flask_client import OAuth
from dotenv import load_dotenv
import json

# Load environment variables from .env file
load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
oauth = OAuth()

def create_app():
    app = Flask(__name__)
    
    # Load configuration from environment variables
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI')
    app.config['GOOGLE_CLIENT_ID'] = os.getenv('GOOGLE_CLIENT_ID')
    
    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)

    login_manager.login_view = 'auth.google_login'

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .auth import auth
    from .views import views

    # Register blueprints
    app.register_blueprint(auth)
    app.register_blueprint(views)

    with app.app_context():
        db.create_all()

    Migrate(app, db)

    @app.template_filter('to_json')
    def to_json(value):
        return json.dumps(value)

    @app.template_filter('from_json')
    def from_json(value):
        return json.loads(value)

    return app
