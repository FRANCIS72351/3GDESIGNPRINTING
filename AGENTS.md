# AGENTS.md

## Cursor Cloud specific instructions

This is a single Flask + SQLite ERP web app ("3G Design" / Printing Shop). There is one
service: the Flask web app. There is no separate frontend build, no external database, and
no message broker — SQLite is used as a local file DB (`3G_ERP_V1.db`, auto-created).

### Environment
- Python dependencies are installed into a project virtualenv at `.venv` by the startup
  update script (`python3 -m venv .venv` + `pip install -r requirements.txt`). Always run
  Python via `.venv/bin/python` (or activate it with `. .venv/bin/activate`).
- There is no formal test suite or linter configured. The `test_*.py` / `*_2fa.py` /
  `fix*.py` files in the repo root are ad-hoc maintenance scripts, not pytest tests.
  A reasonable syntax sanity check is `python -m py_compile app.py models.py run.py`.

### Running the app
- Start the app with `python run.py` (uses the Waitress WSGI server). It binds
  `0.0.0.0:5001`; open it at `http://127.0.0.1:5001/`. Port is overridable via `APP_PORT`.
- On first run, `run.py` calls `db.create_all()` and seeds two admin accounts:
  - `admin` / `Press2026!` — 2FA is NOT yet enabled, so the first login redirects to
    `/setup-2fa` to enroll an authenticator.
  - `ghost_admin` / `Ghost2026!` — super-admin ("ghost") with 2FA enabled.
- An `.env` file is optional for a basic run (the app falls back to a dev `SECRET_KEY`).
  Copy `.env.example` to `.env` to configure secrets; `.env` is gitignored. External
  integrations (Twilio, AssemblyAI, WhatsApp/Meta, Gmail) are all optional and the app
  starts fine with them blank.

### Logging in / 2FA (non-obvious)
- The TOTP secret for each admin is printed by `run.py` at account-creation time and is
  also readable from the DB (`Admin.otp_secret`). To complete login programmatically or in
  the browser, generate the current code with
  `python -c "import pyotp; print(pyotp.TOTP('<secret>').now())"`.
- 2FA verification uses a wide validity window (`valid_window=10`, i.e. roughly ±5 minutes),
  so a generated TOTP code stays valid long enough to type into the browser manually.
- Login flow: POST `/login` (username + password) -> `/setup-2fa` (first time) or
  `/verify-2fa` -> on success lands on `/dashboard` (or `/ghost` for `ghost_admin`).

### Resetting state
- To reset all data, stop the app and delete `3G_ERP_V1.db` (plus any `*.db-wal` /
  `*.db-shm` files); the next `python run.py` recreates and reseeds it.
