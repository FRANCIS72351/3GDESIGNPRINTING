#!/usr/bin/env python3
"""Initialize database tables and system settings (run once after deploy)."""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, '.env'))

from app import app
from models import db, Admin, SystemSettings
from server_stability import ensure_system_settings


def main():
    with app.app_context():
        db.create_all()
        ensure_system_settings(db, SystemSettings)
        admin_count = Admin.query.count()
        print(f'Database ready at {app.config["DATABASE_FILE"]}')
        print(f'Admin accounts: {admin_count}')
        if admin_count == 0:
            print('No admins yet — run: python create_ghost.py')


if __name__ == '__main__':
    main()
