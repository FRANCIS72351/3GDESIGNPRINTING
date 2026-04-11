import sys
import os
from dotenv import load_dotenv

# Add the current directory to the path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.append(path)

# Load environment variables
load_dotenv(os.path.join(path, '.env'))

# Import the Flask application
from app import app as application

# PythonAnywhere sets this environment variable
if 'PYTHONANYWHERE_DOMAIN' in os.environ:
    # Production settings for PythonAnywhere
    application.config['PREFERRED_URL_SCHEME'] = 'https'
    # Ensure static files are served correctly
    application.config['DEBUG'] = False
else:
    # Development settings
    application.config['DEBUG'] = True
app = application
