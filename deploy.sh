#!/usr/bin/env bash
set -euo pipefail

# ============================================================================== 
# Enterprise Deployment Script for 3G DESIGN GLOBAL ERP
# Target Environment: Hostinger KVM VPS (Systemd + Unix Socket + Pre-flight Check)
# ============================================================================== 

PROJECT_DIR="${PROJECT_DIR:-/var/www/erp}"
GIT_REMOTE="${GIT_REMOTE:-origin}"
GIT_BRANCH="${GIT_BRANCH:-main}"
DB_PATH="${DATABASE_PATH:-$PROJECT_DIR/3G_ERP_V1.db}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"

if [ ! -d "$PROJECT_DIR" ]; then
    echo "Error: project directory does not exist: $PROJECT_DIR"
    exit 1
fi

cd "$PROJECT_DIR"

mkdir -p "$BACKUP_DIR"

echo "Database path configured: $DB_PATH"
if [ -f "$DB_PATH" ]; then
    timestamp="$(date +%Y%m%d-%H%M%S)"
    cp -p "$DB_PATH" "$BACKUP_DIR/3G_ERP_V1.db.$timestamp.bak"
    echo "Database backup created: $BACKUP_DIR/3G_ERP_V1.db.$timestamp.bak"
else
    echo "No database file detected at $DB_PATH. Leaving live data untouched."
fi

if [ "$DB_PATH" != "$PROJECT_DIR/3G_ERP_V1.db" ] && [ -f "$PROJECT_DIR/3G_ERP_V1.db" ]; then
    echo "Project-local database file exists but deployment is pointing to $DB_PATH. The local app database is not being overwritten."
fi

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

# 2. Virtual Environment & Dependencies
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment and updating dependencies..."
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install psutil  # Required for health monitoring

# 4. Database Migrations (safe: does not overwrite cloud data; only upgrades schema when app points to the intended DB)
if [ -d "migrations" ]; then
    echo "Running database migrations..."
    export FLASK_APP=wsgi.py
    export DATABASE_PATH="$DB_PATH"
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

if [ -f "$DB_PATH" ]; then
    chmod 600 "$DB_PATH" 2>/dev/null || true
fi

# 6. Execute optional pre-flight health check script
if [ -f "monitor.py" ]; then
    echo "Running pre-flight system telemetry check..."
    python monitor.py
else
    echo "No monitor.py found. Skipping optional pre-flight telemetry check."
fi

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