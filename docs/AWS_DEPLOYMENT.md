# AWS Deployment Guide — Olatricity ERP

This guide deploys the Flask + SQLite ERP on **Amazon EC2** with **nginx**, **Gunicorn**, and **systemd**. This is the recommended approach for SQLite because the database and uploads must live on a **persistent EBS volume** attached to a single instance.

An optional **Docker** path (EC2 or ECS) is included at the end.

---

## Architecture

```
Internet → Route 53 (optional) → EC2 (security group :80/:443)
                                    ├── nginx (static + reverse proxy)
                                    └── Gunicorn → Flask app → SQLite on EBS
```

| Component | Role |
|-----------|------|
| **EC2** | Single app server (t3.small or t3.medium recommended) |
| **EBS** | Persistent SQLite DB + uploads (`/var/lib/olatricity`) |
| **nginx** | HTTPS termination, `/static/` serving, proxy to Gunicorn |
| **Gunicorn** | Production WSGI server (`wsgi:application`) |
| **systemd** | Auto-start and restart on failure |

---

## Prerequisites

- AWS account
- Domain name (optional but required for WhatsApp/Twilio HTTPS webhooks)
- SSH key pair
- `.env` values from [`.env.production.example`](../.env.production.example)

Generate a secret key locally:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 1 — Launch EC2

1. **AMI:** Ubuntu Server 22.04 LTS or 24.04 LTS (64-bit x86)
2. **Instance type:** `t3.small` (2 GB RAM) minimum; `t3.medium` for heavier traffic
3. **Storage:** Root volume 20 GB + optional dedicated **EBS data volume** 20–50 GB
4. **Key pair:** Create or select an existing SSH key
5. **Security group inbound rules:**

   | Port | Source | Purpose |
   |------|--------|---------|
   | 22 | Your IP | SSH |
   | 80 | 0.0.0.0/0 | HTTP (certbot + redirect) |
   | 443 | 0.0.0.0/0 | HTTPS |

6. Launch the instance and note the **public IP** or attach an **Elastic IP**.

### Mount a dedicated EBS volume (recommended)

If you added a separate data volume (e.g. `/dev/nvme1n1`):

```bash
sudo mkfs.ext4 /dev/nvme1n1          # only once on a new volume
sudo mkdir -p /var/lib/olatricity
echo '/dev/nvme1n1 /var/lib/olatricity ext4 defaults,nofail 0 2' | sudo tee -a /etc/fstab
sudo mount -a
sudo chown olatricity:olatricity /var/lib/olatricity   # after user is created
```

Set in `.env`:

```
DATABASE_PATH=/var/lib/olatricity/data/3G_ERP_V1.db
```

The install script creates `/var/lib/olatricity/data` automatically.

---

## Step 2 — Deploy the application

SSH into the instance:

```bash
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
```

### Option A — Automated install (from repo on server)

Upload or clone the project, then run:

```bash
cd /path/to/Olatricity
sudo DOMAIN=erp.yourdomain.com bash deploy/install-ec2.sh
```

Or clone directly:

```bash
sudo REPO_URL=https://github.com/YOUR_ORG/Olatricity.git DOMAIN=erp.yourdomain.com bash deploy/install-ec2.sh
```

### Option B — Manual steps

```bash
sudo apt update && sudo apt install -y python3 python3-venv nginx certbot python3-certbot-nginx git

sudo useradd --system --home /opt/olatricity --shell /usr/sbin/nologin olatricity || true
sudo mkdir -p /opt/olatricity /var/lib/olatricity/data /var/log/olatricity

# Copy project files to /opt/olatricity (git clone, rsync, or scp)
cd /opt/olatricity
sudo python3 -m venv venv
sudo ./venv/bin/pip install -r requirements.txt

sudo cp .env.production.example .env
sudo nano .env   # set SECRET_KEY, PUBLIC_SITE_URL, DATABASE_PATH, etc.

sudo -u olatricity bash -c 'cd /opt/olatricity && set -a && source .env && set +a && ./venv/bin/python scripts/init_app.py'

sudo cp deploy/systemd/olatricity.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now olatricity

sudo cp deploy/nginx/olatricity-http.conf /etc/nginx/sites-available/olatricity
# Edit server_name to your domain
sudo ln -sf /etc/nginx/sites-available/olatricity /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

---

## Step 3 — Configure environment

Edit `/opt/olatricity/.env`:

```bash
sudo nano /opt/olatricity/.env
```

**Required:**

| Variable | Example |
|----------|---------|
| `FLASK_ENV` | `production` |
| `SECRET_KEY` | 64-char hex from `secrets.token_hex(32)` |
| `PUBLIC_SITE_URL` | `https://erp.yourdomain.com` |
| `DATABASE_PATH` | `/var/lib/olatricity/data/3G_ERP_V1.db` |

Restart after changes:

```bash
sudo systemctl restart olatricity
```

---

## Step 4 — Create admin account

```bash
cd /opt/olatricity
sudo -u olatricity ./venv/bin/python create_ghost.py
```

Save the printed credentials securely. Use the ghost admin to manage team accounts.

---

## Step 5 — DNS and SSL

1. Create an **A record** pointing `erp.yourdomain.com` → EC2 Elastic IP
2. Obtain Let's Encrypt certificate:

```bash
sudo certbot --nginx -d erp.yourdomain.com
```

Certbot updates nginx for HTTPS automatically. Renewal is handled by a systemd timer.

Verify:

```bash
curl https://erp.yourdomain.com/health
# {"database":"connected","status":"ok"}
```

---

## Step 6 — Verify and monitor

```bash
# App health (direct)
curl http://127.0.0.1:8000/health

# Service status
sudo systemctl status olatricity
sudo journalctl -u olatricity -f

# App log file
sudo tail -f /var/log/olatricity/olatricity.log

# nginx logs
sudo tail -f /var/log/nginx/olatricity.access.log
```

### Health check

`GET /health` returns `200` when SQLite is reachable. Use this for:
- Load balancer target group health checks (if you add an ALB later)
- Uptime monitoring (UptimeRobot, CloudWatch synthetic canaries)

---

## Backups

SQLite lives on EBS. Back up regularly:

```bash
# Manual backup via app (Ghost dashboard) or shell:
sudo -u olatricity sqlite3 /var/lib/olatricity/data/3G_ERP_V1.db ".backup '/var/lib/olatricity/backups/erp_$(date +%Y%m%d).db'"
```

**EBS snapshots:** Schedule daily snapshots in AWS Console → EC2 → Elastic Block Store → Lifecycle Manager.

Also back up `/opt/olatricity/static/uploads` (user uploads).

---

## Updates (redeploy)

```bash
cd /opt/olatricity
sudo -u olatricity git pull          # if deployed via git
sudo ./venv/bin/pip install -r requirements.txt
sudo -u olatricity bash -c 'set -a && source .env && set +a && ./venv/bin/python scripts/init_app.py'
sudo systemctl restart olatricity
```

---

## Optional — Docker on EC2

For containerized deployment on the same EC2 instance:

```bash
cp .env.production.example .env
# Edit .env — set SECRET_KEY, PUBLIC_SITE_URL, etc.

docker compose build
docker compose up -d
docker compose exec olatricity python scripts/init_app.py
docker compose exec olatricity python create_ghost.py
```

Point nginx at `127.0.0.1:8000` (same as the systemd setup). Data persists in Docker volumes `olatricity_data` and `olatricity_uploads`.

### ECS (advanced)

1. Push image to **ECR**
2. Create ECS task definition using the Dockerfile `CMD`
3. Mount **EFS** at `/data` for SQLite (EFS supports concurrent access but SQLite still prefers single-writer — stick to one task)
4. Use an ALB with health check path `/health`

---

## Security checklist

- [ ] `SECRET_KEY` is unique and not committed to git
- [ ] `.env` is on the server only (listed in `.gitignore`)
- [ ] SSH restricted to your IP (security group)
- [ ] HTTPS enabled via certbot
- [ ] Default admin passwords from dev are **not** used — run `create_ghost.py` and change credentials
- [ ] EBS snapshots enabled
- [ ] `LOCAL_API_KEY` set if using shop PC call tracker

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `502 Bad Gateway` | Check `systemctl status olatricity`; app may not be on port 8000 |
| `SECRET_KEY must be set` | Add `SECRET_KEY` to `.env`, restart service |
| DB permission errors | `sudo chown -R olatricity:olatricity /var/lib/olatricity` |
| WhatsApp webhooks fail | Confirm `PUBLIC_SITE_URL` is HTTPS and reachable |
| nginx won't start (SSL) | Use `olatricity-http.conf` until certbot runs |

---

## Files reference

| File | Purpose |
|------|---------|
| `wsgi.py` | WSGI entry for Gunicorn |
| `gunicorn.conf.py` | Worker/thread settings |
| `run.py` | Waitress dev/production runner (Windows-friendly) |
| `scripts/init_app.py` | Create DB tables after deploy |
| `deploy/install-ec2.sh` | One-shot EC2 bootstrap |
| `deploy/nginx/olatricity-http.conf` | HTTP nginx (pre-SSL) |
| `deploy/nginx/olatricity.conf` | Full HTTPS nginx template |
| `deploy/systemd/olatricity.service` | systemd unit |
| `Dockerfile` / `docker-compose.yml` | Container deployment |
| `.env.production.example` | Production env template |
