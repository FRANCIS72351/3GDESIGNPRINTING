# Deploying to PythonAnywhere (demo hosting)

This Flask + SQLite app runs well on a single PythonAnywhere web worker. The repo is
already deployment-ready: `wsgi.py` detects `PYTHONANYWHERE_DOMAIN` and `app.py` creates the
SQLite tables automatically on import. Follow the steps below in your PythonAnywhere account.

> Replace `<USER>` with your PythonAnywhere username throughout. The project is assumed to
> live at `/home/<USER>/3GDESIGNPRINTING`.

## 1. Get the code onto PythonAnywhere
Open a **Bash console** (Consoles tab) and clone the public repo:

```bash
git clone https://github.com/FRANCIS72351/3GDESIGNPRINTING.git
```

## 2. Create a virtualenv and install dependencies
```bash
mkvirtualenv --python=/usr/bin/python3.10 3gerp
cd ~/3GDESIGNPRINTING
pip install -r requirements.txt
```
(Python 3.10 is the safe default on PythonAnywhere; 3.12 also works — validated locally.)

## 3. Create a `.env` file
The app reads `/home/<USER>/3GDESIGNPRINTING/.env` (loaded by `wsgi.py`). At minimum set a
secret key:
```bash
cd ~/3GDESIGNPRINTING
python -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))" > .env
echo "GHOST_ADMIN_USER=ghost_admin" >> .env
```
All third-party integrations (Twilio, AssemblyAI, WhatsApp/Meta, Gmail) are optional and can
stay blank for a demo.

## 4. Seed an admin login
Tables are created on first import, but login accounts are not. Seed them once (with the
virtualenv active and inside the project dir):
```bash
python create_ghost.py        # creates ghost_admin / Ghost2026! (prints its TOTP secret)
python - <<'PY'
from app import app, db
from models import Admin
from werkzeug.security import generate_password_hash
import pyotp, secrets
with app.app_context():
    if not Admin.query.filter_by(username='admin').first():
        db.session.add(Admin(
            username='admin',
            password_hash=generate_password_hash('Press2026!', method='pbkdf2:sha256'),
            email='admin@press.com',
            otp_secret=pyotp.random_base32(),
            recovery_key=generate_password_hash(
                ''.join(secrets.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') for _ in range(8)),
                method='pbkdf2:sha256'),
            two_fa_enabled=False))
        db.session.commit()
        print('admin created -> admin / Press2026! (set up 2FA on first login)')
    else:
        print('admin already exists')
PY
```
Save the printed TOTP secret(s) — you need an authenticator app to log in.

## 5. Create the web app (Web tab)
1. **Web** tab → **Add a new web app** → **Manual configuration** → **Python 3.10**.
2. **Virtualenv**: set to `/home/<USER>/.virtualenvs/3gerp`.
3. **WSGI configuration file**: click it and replace the contents with:
   ```python
   import sys
   project_home = '/home/<USER>/3GDESIGNPRINTING'
   if project_home not in sys.path:
       sys.path.insert(0, project_home)
   from wsgi import application  # noqa: E402,F401
   ```
4. **Static files** mapping: URL `/static/` → Directory `/home/<USER>/3GDESIGNPRINTING/static/`.
5. Click the green **Reload** button.

## 6. Log in
- URL: `https://<USER>.pythonanywhere.com/login`
- Username `admin`, password `Press2026!` → first login walks you through 2FA enrollment
  (scan the QR with an authenticator app), then lands on the dashboard.
- `ghost_admin` / `Ghost2026!` is the super-admin (2FA already enabled; use the TOTP secret
  printed in step 4).

## Notes
- SQLite (`3G_ERP_V1.db`) lives in the project directory and is fine for a single-worker demo.
- 2FA codes have a wide validity window (~±5 min), so manual entry is forgiving.
- To redeploy after changes: `git pull` in the console, then hit **Reload** on the Web tab.
