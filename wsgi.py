import sys
import os
from dotenv import load_dotenv

# 1. Point to your folder
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.append(path)

# 2. Load your secret .env file
load_dotenv(os.path.join(path, '.env'))

# 3. Import your app
from app import app as application
app = application
