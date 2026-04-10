# Printing Shop Application

A modern Flask-based printing shop management system with voice ordering capabilities.

## Features

- Admin dashboard with 2FA authentication
- Voice call recording and transcription
- Product management
- Customer order tracking
- Email notifications
- WhatsApp integration

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirement.txt
   ```

2. Set up environment variables in `.env` file:
   ```
   SECRET_KEY=your-secret-key-here
   ASSEMBLYAI_API_KEY=your-assemblyai-key
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-email-password
   TWILIO_ACCOUNT_SID=your-twilio-sid
   TWILIO_AUTH_TOKEN=your-twilio-token
   ```

3. Initialize the database:
   ```bash
   python -c "from app import db; db.create_all()"
   ```

## Running the Application

### Development Mode
```bash
python run.py
```

### Production Mode (Recommended)
```bash
# Using Gunicorn (single worker)
gunicorn --bind 0.0.0.0:8000 wsgi:app

# Using Gunicorn (multiple workers for better performance)
gunicorn --bind 0.0.0.0:8000 --workers 4 wsgi:app

# Using Gunicorn with configuration file
gunicorn --config gunicorn.conf.py wsgi:app
```

### Alternative Production Commands
```bash
# Using Python's built-in WSGI server (not recommended for production)
python wsgi.py

# Using Waitress (another WSGI server option)
pip install waitress
waitress-serve --host 0.0.0.0 --port 8000 wsgi:app
```

## Server Configuration

The application is configured to use Gunicorn as the production WSGI server. Key benefits:
- Production-ready performance
- Automatic worker management
- Request load balancing
- Graceful restarts

## Default Access

- Application: http://localhost:8000 (production) or http://localhost:5000 (development)
- Admin Login: http://localhost:8000/login
- Default admin credentials: admin / 

## Deployment Notes

For production deployment:
1. Use a reverse proxy like Nginx
2. Set up SSL/TLS certificates
3. Configure environment variables securely
4. Use a process manager like systemd or supervisor
5. Set up logging and monitoring