#!/usr/bin/env bash
# Bootstrap Olatricity on Ubuntu 22.04/24.04 EC2.
# Run as root: sudo bash deploy/install-ec2.sh
set -euo pipefail

APP_USER="${APP_USER:-olatricity}"
APP_DIR="${APP_DIR:-/opt/olatricity}"
DATA_DIR="${DATA_DIR:-/var/lib/olatricity/data}"
LOG_DIR="${LOG_DIR:-/var/log/olatricity}"
DOMAIN="${DOMAIN:-erp.yourdomain.com}"
REPO_URL="${REPO_URL:-}"

echo "==> Installing system packages..."
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx git rsync

echo "==> Creating service user and directories..."
id -u "$APP_USER" &>/dev/null || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_DIR" "$DATA_DIR" "$LOG_DIR" /var/www/certbot
chown -R "$APP_USER:$APP_USER" "$DATA_DIR" "$LOG_DIR"

if [[ -n "$REPO_URL" ]]; then
  echo "==> Cloning repository..."
  if [[ ! -d "$APP_DIR/.git" ]]; then
    git clone "$REPO_URL" "$APP_DIR"
  else
    git -C "$APP_DIR" pull
  fi
else
  echo "==> Syncing project files to $APP_DIR (run from repo root)..."
  rsync -a --delete \
    --exclude '.git' --exclude 'venv' --exclude '__pycache__' \
    --exclude '*.db' --exclude '*.db-shm' --exclude '*.db-wal' \
    --exclude '.env' \
    ./ "$APP_DIR/"
fi

echo "==> Creating Python virtualenv..."
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --upgrade pip
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then
  cp "$APP_DIR/.env.production.example" "$APP_DIR/.env"
  echo ""
  echo "!! Edit $APP_DIR/.env before starting (SECRET_KEY, PUBLIC_SITE_URL, etc.)"
  echo "   Generate SECRET_KEY: python3 -c \"import secrets; print(secrets.token_hex(32))\""
  echo ""
fi

# Ensure DATABASE_PATH in .env points to persistent volume
grep -q '^DATABASE_PATH=' "$APP_DIR/.env" || echo "DATABASE_PATH=$DATA_DIR/3G_ERP_V1.db" >> "$APP_DIR/.env"
grep -q '^LOG_DIR=' "$APP_DIR/.env" || echo "LOG_DIR=$LOG_DIR" >> "$APP_DIR/.env"
grep -q '^APP_PORT=' "$APP_DIR/.env" || echo "APP_PORT=8000" >> "$APP_DIR/.env"
grep -q '^FLASK_ENV=' "$APP_DIR/.env" || echo "FLASK_ENV=production" >> "$APP_DIR/.env"

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

echo "==> Initializing database..."
sudo -u "$APP_USER" bash -c "cd $APP_DIR && set -a && source .env && set +a && ./venv/bin/python scripts/init_app.py"

echo "==> Installing systemd service..."
cp "$APP_DIR/deploy/systemd/olatricity.service" /etc/systemd/system/olatricity.service
systemctl daemon-reload
systemctl enable olatricity

echo "==> Configuring nginx (HTTP initially — run certbot for HTTPS)..."
sed "s/erp.yourdomain.com/$DOMAIN/g" "$APP_DIR/deploy/nginx/olatricity-http.conf" > /etc/nginx/sites-available/olatricity
ln -sf /etc/nginx/sites-available/olatricity /etc/nginx/sites-enabled/olatricity
rm -f /etc/nginx/sites-enabled/default
nginx -t

echo "==> Starting services..."
systemctl restart olatricity
systemctl restart nginx

echo ""
echo "Deploy complete."
echo "  App health:  curl http://127.0.0.1:8000/health"
echo "  Create admin: cd $APP_DIR && sudo -u $APP_USER ./venv/bin/python create_ghost.py"
echo "  SSL:         certbot --nginx -d $DOMAIN"
echo "  Logs:        journalctl -u olatricity -f"
