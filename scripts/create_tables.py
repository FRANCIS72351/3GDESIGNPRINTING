"""Create any missing tables in the database (safe one-time helper).
Run with the venv active:
    python scripts/create_tables.py
"""
from app import app, db

with app.app_context():
    db.create_all()
    print('create_all() completed - ensure migrations are used in production (Alembic recommended).')
