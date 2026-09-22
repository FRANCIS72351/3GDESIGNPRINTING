# AGENTS.md

## Cursor Cloud specific instructions

### What this is
Single-service **Flask ERP** ("3G DESIGN ERP") for a print shop. Pure Python, **SQLite** DB
(`3G_ERP_V1.db`, auto-created on first run). All third-party integrations (Twilio, WhatsApp/Meta,
OpenAI, AssemblyAI, Flask-Mail) are optional and guarded — none are needed to run or test locally.

### Dependencies / environment
- Python deps are installed into a project venv at `./venv` by the startup update script
  (`pip install -r requirements.txt`). Always run Python via `./venv/bin/python`.
- `.env` is gitignored. The app runs without it (falls back to a dev `SECRET_KEY`). To exercise
  full config, copy `.env.example` to `.env`; only `SECRET_KEY` matters for local dev.

### Running the app (dev)
- `./venv/bin/python run.py` — serves with Waitress on `APP_PORT` (default **5001**) at
  `http://0.0.0.0:5001`. This is the dev runner per the README. (`wsgi.py` / gunicorn are for prod.)
- On first run, `run.py` seeds two admins and **prints their TOTP secrets/passwords to stdout**.
  Because `serve()` blocks, stdout is buffered — if you piped through `tee`, the seed banner may not
  flush. Instead read the seeded values straight from the DB:
  `./venv/bin/python -c "from app import app; from models import Admin; ctx=app.app_context(); ctx.push(); [print(a.username, a.otp_secret) for a in Admin.query.all()]"`

### Logging in (2FA is mandatory)
- Default admin: username `admin`, password `Press2026!`. Login is two-step: `/login` →
  `/verify-2fa` (TOTP). Generate the current code from the stored secret:
  `./venv/bin/python -c "import pyotp; print(pyotp.TOTP('<otp_secret>').now())"`.
- `/verify-2fa` uses `valid_window=10` (~±5 min tolerance), so a precomputed OTP is fine for manual
  or scripted testing.
- There is also a `ghost_admin` super-user (password `Ghost2026!`) that lands on `/ghost-dashboard`.

### Lint / test / build
- No linter, no `pyproject.toml`/CI, and **no real test suite**. Root `test_*.py` files are ad-hoc
  scripts, not pytest: `test_login_http.py` POSTs to a running server on :5001; `test_password.py`
  opens an app context and checks the admin hash. Run them with `./venv/bin/python <file>`.
- "Build" = there is no build step; running `run.py` is the validation path.

### Gotchas
- Some dashboard links point at routes that 404 (e.g. `/admin/product`); the working inventory page
  is `/admin/inventory` with the add form at `/admin/add_product`. These are pre-existing app quirks,
  not environment problems.
