from flask import Blueprint, redirect, url_for, request, session
from flask_login import login_user, logout_user, login_required
from dotenv import load_dotenv
import os
from .models import User
from . import db, oauth
load_dotenv()

auth = Blueprint('auth', __name__)

# ✅ Google OAuth Setup using OpenID Connect (Now Using .env)
google = oauth.register(
    name='google', 
    client_id=os.getenv("OAUTH_GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("OAUTH_GOOGLE_CLIENT_SECRET"),
    server_metadata_url=os.getenv("OAUTH_GOOGLE_METADATA_URL"),
    client_kwargs={"scope": os.getenv("OAUTH_GOOGLE_SCOPE", "openid email profile")}
)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for('views.home'))  # Ensure 'views.home' is the correct route

@auth.route('/google-login')
def google_login():
    redirect_uri = url_for('auth.google_authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@auth.route('/google-auth')
def google_authorize():
    token = google.authorize_access_token()
    
    user_info = token.get('userinfo')
    if user_info is None:
        user_info = google.get('userinfo').json()
    
    user = User.query.filter_by(google_id=user_info['sub']).first()
    if not user:
        user = User(
            google_id=user_info['sub'],
            email=user_info['email'],
            name=user_info.get('name', 'No Name')  
        )
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    return redirect(url_for('views.dashboard'))
