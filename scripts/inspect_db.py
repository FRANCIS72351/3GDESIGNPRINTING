#!/usr/bin/env python3
"""List SQLite database files and admin accounts for Olatricity diagnostics."""
import argparse
import glob
import os
import sqlite3
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, '.env'))

from app import app  # noqa: E402


def _discover_db_files():
    patterns = [
        os.path.join(project_root, '*.db'),
        os.path.join(project_root, '*.db.backup_*'),
        os.path.join(project_root, 'instance', '*.db'),
        os.path.join(project_root, 'instance', '*.db.backup_*'),
    ]
    found = []
    for pattern in patterns:
        found.extend(glob.glob(pattern))
    return sorted(set(found))


def _inspect_file(db_path):
    result = {
        'path': db_path,
        'exists': os.path.exists(db_path),
        'size_bytes': None,
        'has_admin_table': False,
        'admin_columns': [],
        'admin_rows': [],
        'error': None,
    }
    if not result['exists']:
        result['error'] = 'missing'
        return result

    result['size_bytes'] = os.path.getsize(db_path)
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admin'")
        if not cur.fetchone():
            conn.close()
            return result

        result['has_admin_table'] = True
        cur.execute('PRAGMA table_info(admin)')
        result['admin_columns'] = [row[1] for row in cur.fetchall()]
        cur.execute(
            'SELECT id, username, role, email, two_fa_enabled FROM admin ORDER BY id'
        )
        result['admin_rows'] = cur.fetchall()
        conn.close()
    except sqlite3.Error as exc:
        result['error'] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser(description='Inspect Olatricity SQLite databases')
    parser.add_argument(
        '--files',
        nargs='*',
        help='Specific database files to inspect (default: auto-discover)',
    )
    args = parser.parse_args()

    with app.app_context():
        active_db = app.config['DATABASE_FILE']

    print('=== Active application database ===')
    print(f'DATABASE_FILE: {active_db}')
    print(f'Exists: {os.path.exists(active_db)}')
    print()

    files = args.files or _discover_db_files()
    if active_db not in files and os.path.exists(active_db):
        files = [active_db] + files

    print('=== Database files ===')
    for db_path in files:
        info = _inspect_file(db_path)
        rel = os.path.relpath(info['path'], project_root)
        marker = ' <-- ACTIVE' if os.path.abspath(info['path']) == os.path.abspath(active_db) else ''
        print(f'\n{rel}{marker}')
        if info['error'] == 'missing':
            print('  status: MISSING')
            continue
        if info['error']:
            print(f'  status: ERROR ({info["error"]})')
            continue
        print(f'  size: {info["size_bytes"]} bytes')
        if not info['has_admin_table']:
            print('  admin table: (not present)')
            continue
        print(f'  admin columns ({len(info["admin_columns"])}): {", ".join(info["admin_columns"])}')
        if not info['admin_rows']:
            print('  admin users: (empty)')
        else:
            print('  admin users:')
            for row in info['admin_rows']:
                admin_id, username, role, email, two_fa = row
                print(
                    f'    id={admin_id} username={username!r} role={role!r} '
                    f'email={email!r} 2fa={two_fa}'
                )


if __name__ == '__main__':
    main()
