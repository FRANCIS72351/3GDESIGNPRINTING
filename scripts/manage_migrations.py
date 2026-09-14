"""Helper to run Flask-Migrate commands programmatically.

Usage (after installing requirements):
    python -m flask db init
    python -m flask db migrate -m "Add document audit"
    python -m flask db upgrade

You can also run this script directly if you set FLASK_APP=app.py
"""
# This file exists to document commands and provide helper references.
# The actual migration CLI uses the `flask` command (Flask-Migrate / Alembic).
print('Use the flask CLI with Flask-Migrate:')
print('  set FLASK_APP=app.py')
print('  flask db init')
print('  flask db migrate -m "Create DocumentAudit"')
print('  flask db upgrade')
