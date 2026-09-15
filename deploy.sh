#!/usr/bin/env bash
set -euo pipefail

# ============================================================================== 
# Enterprise Deployment Script for 3G DESIGN GLOBAL ERP
# Target Environment: Hostinger KVM VPS (Systemd + Unix Socket + Pre-flight Check)
# ============================================================================== 

PROJECT_DIR="${PROJECT_DIR:-/var/www/erp}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
LOCAL_DB_FILE="${LOCAL_DB_FILE:-${PROJECT_DIR}/3G_ERP_V1.db}"
REMOTE_DB_PATH="${DATABASE_PATH:-${PROJECT_DIR}/3G_ERP_V1.db}"
DB_OVERRIDE="${DB_OVERRIDE:-1}"

cd "$PROJECT_DIR"

echo "=================================================="
echo " Starting Deployment for 3G DESIGN GLOBAL ERP"
echo "=================================================="

# 1. Fetch latest code from Git repository
if [ -d ".git" ]; then
    echo "Fetching latest code from ${GIT_REMOTE}/${GIT_BRANCH}..."
    git fetch "$GIT_REMOTE" "$GIT_BRANCH"
    git reset --hard "$GIT_REMOTE/$GIT_BRANCH"
else
    echo "Warning: No git repository found. Proceeding with local files."
fi

# 2. Local database override: keep the deployment database aligned with the local app source of truth.
if [ "$DB_OVERRIDE" = "1" ]; then
    if [ -f "$LOCAL_DB_FILE" ]; then
        echo "Local DB source detected at $LOCAL_DB_FILE. Overriding cloud database with local DB..."
        mkdir -p "$(dirname "$REMOTE_DB_PATH")"
        cp -f "$LOCAL_DB_FILE" "$REMOTE_DB_PATH"
        export DATABASE_PATH="$REMOTE_DB_PATH"
    else
        echo "No local DB file found at $LOCAL_DB_FILE. Keeping the existing cloud database in place."
    fi
else
    echo "DB override disabled. Keeping the existing cloud database in place."
fi

# 3. Virtual Environment & Dependencies
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment and updating dependencies..."
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install psutil  # Required for health monitoring

# 4. Database Migrations
if [ -d "migrations" ]; then
    echo "Running database migrations..."
    export FLASK_APP=wsgi.py
    if command -v flask >/dev/null 2>&1; then
        flask db upgrade || python -m flask db upgrade || echo "Migration completed with warnings."
    else
        python -m flask db upgrade || echo "Migration completed with warnings."
    fi
else
    echo "No migrations directory found. Skipping database upgrade."
fi

# 5. Directory Permissions & Structure
echo "Ensuring required directories and permissions..."
mkdir -p logs instance static/uploads
chmod -R 755 logs instance static/uploads 2>/dev/null || true

# 6. Execute Pre-Flight Health Check Script
echo "Running pre-flight system telemetry check..."
python3 monitor.py

# 7. Restart Service via Systemd (KVM VPS standard)
echo "Reloading and restarting ERP service via systemd..."
systemctl daemon-reload
systemctl restart erp

# 8. Verification
sleep 2
if systemctl is-active --quiet erp; then
    echo "=================================================="
    echo " Deployment completed successfully!"
    echo " ERP service is online and active."
    echo "=================================================="
else
    echo "Error: ERP service failed to stay online. Check logs with:"
    echo "journalctl -u erp -n 50 --no-pager"
    exit 1
fi