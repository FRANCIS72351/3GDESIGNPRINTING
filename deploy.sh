#!/usr/bin/env bash
set -euo pipefail

# Hostinger-safe deployment script for Olatricity.
# Usage:
#   PROJECT_DIR=/home/username/public_html/olatricity ./deploy.sh
#   GIT_BRANCH=main GIT_REMOTE=origin PYTHON_BIN=python3 ./deploy.sh
#
# This script intentionally avoids systemd, sudo, and Hostinger-specific
# package-manager assumptions. It is designed for an SSH/cron shell on
# Hostinger's Linux hosting profile where Gunicorn is run directly.

PROJECT_DIR="${PROJECT_DIR:-$(pwd)}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-.venv}"
APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
LOG_DIR="${LOG_DIR:-${PROJECT_DIR}/logs}"
TMP_DIR="${TMP_DIR:-${PROJECT_DIR}/.tmp}"
PID_FILE="${PID_FILE:-${PROJECT_DIR}/gunicorn.pid}"

cd "$PROJECT_DIR"

# Make sure we are in the git repo and the app entrypoint is available.
if [ ! -f "wsgi.py" ]; then
    echo "Error: wsgi.py not found in $PROJECT_DIR. Run this from the Olatricity project root."
    exit 1
fi

mkdir -p "$LOG_DIR" "$TMP_DIR"

echo "Starting Hostinger deployment for Olatricity..."
echo "Project directory: $PROJECT_DIR"

echo "Fetching latest code from ${GIT_REMOTE}/${GIT_BRANCH}..."
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git fetch "$GIT_REMOTE" "$GIT_BRANCH"
    git reset --hard "$GIT_REMOTE/$GIT_BRANCH"
else
    echo "Warning: No git repository found. Continuing with the files that already exist locally."
fi

echo "Preparing Python virtual environment..."
if [ -d "$VENV_DIR" ]; then
    echo "Using existing virtual environment at $VENV_DIR"
else
    echo "Creating virtual environment at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

# Upgrade pip and install requirements.
echo "Installing Python dependencies..."
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Run database migrations only when a migrations directory exists.
echo "Running database migrations if the project has them..."
export FLASK_APP=wsgi.py
if [ -d "migrations" ]; then
    if command -v flask >/dev/null 2>&1; then
        flask db upgrade || echo "Migration upgrade finished with warnings."
    else
        python -m flask db upgrade || echo "Migration upgrade finished with warnings."
    fi
else
    echo "No migrations folder found. Skipping database migration upgrade."
fi

# Ensure writable directories exist and adjust permissions for Hostinger PHP/SSH users.
echo "Adjusting file permissions for uploads, instance, and logs..."
mkdir -p "$LOG_DIR" instance static/uploads
chmod -R 755 "$LOG_DIR" instance static/uploads 2>/dev/null || true
chmod -R 755 . "$TMP_DIR" 2>/dev/null || true

# Stop any existing Gunicorn workers that came from a previous deployment.
echo "Restarting the app without systemd/sudo..."
if [ -f "$PID_FILE" ]; then
    OLD_PID="$(cat "$PID_FILE" || true)"
    if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Stopping existing Gunicorn process: $OLD_PID"
        kill "$OLD_PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
fi

# Best-effort cleanup in case some extra gunicorn processes stayed behind.
if command -v pkill >/dev/null 2>&1; then
    pkill -f "gunicorn.*wsgi:application" 2>/dev/null || true
fi

# Start Gunicorn directly for Hostinger. The host-specific reverse proxy (Nginx)
# should forward to port APP_PORT if the user has configured the server.
nohup python -m gunicorn \
    --bind "$APP_HOST:$APP_PORT" \
    --workers "$GUNICORN_WORKERS" \
    --threads "$GUNICORN_THREADS" \
    --timeout 120 \
    --keep-alive 15 \
    --graceful-timeout 30 \
    --access-logfile "$LOG_DIR/gunicorn-access.log" \
    --error-logfile "$LOG_DIR/gunicorn-error.log" \
    wsgi:application \
    > "$LOG_DIR/gunicorn-start.log" 2>&1 &

# Record the background process ID for later restart/cleanup.
SERVER_PID=$!
echo "$SERVER_PID" > "$PID_FILE"

sleep 1
if kill -0 "$SERVER_PID" 2>/dev/null; then
    echo "Gunicorn started successfully with PID $SERVER_PID on ${APP_HOST}:${APP_PORT}."
else
    echo "Gunicorn did not stay up after launch. Check $LOG_DIR/gunicorn-start.log"
    exit 1
fi

echo "Deployment completed successfully!"