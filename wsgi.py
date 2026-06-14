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
    application.config['PREFERRED_URL_SCHEME'] = 'https'
    application.config['DEBUG'] = False
    pa_domain = os.environ['PYTHONANYWHERE_DOMAIN']
    if not os.getenv('PUBLIC_SITE_URL') and not os.getenv('WEBHOOK_BASE_URL'):
        os.environ['PUBLIC_SITE_URL'] = f'https://{pa_domain}'
else:
    application.config['DEBUG'] = True
