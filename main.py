# run.py
import os
from website import create_app


app = create_app()

if __name__ == '__main__':
    # Use environment variable to control debug mode
    # NEVER use debug=True in production
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    
    # Use SSL in development for testing secure cookies
    # In production, use a proper WSGI server (gunicorn) with a reverse proxy (nginx)
    if debug_mode:
        app.run(ssl_context='adhoc', debug=True, host='127.0.0.1', port=5000)
    else:
        # Production mode - no debug, no adhoc SSL (handled by reverse proxy)
        app.run(debug=False, host='0.0.0.0', port=int(os.getenv('PORT', 5000)))