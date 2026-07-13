#!/usr/bin/env python3
"""Restore admin users from a backup SQLite database into the active ERP database."""
import argparse
import glob
import os
import shutil
import sqlite3
import sys
from datetime import datetime

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv(os.path.join(project_root, '.env'))

from app import app  # noqa: E402
from models import Admin  # noqa: E402

ADMIN_COPY_COLUMNS = [
    'id',
    'username',
    'password_hash',
    'email',
    'role',
    'moderator_permissions',
    'otp_secret',
    'recovery_key',
    'two_fa_enabled',
    'failed_2fa_count',
    'last_attempt_time',
    'time_drift',
    'last_login_at',
    'last_login_ip',
    'public_key',
    'encrypted_private_key',
]


def _admin_columns(conn):
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(admin)')
    return [row[1] for row in cur.fetchall()]


def _admin_usernames(conn):
    cur = conn.cursor()
    cur.execute('SELECT username FROM admin ORDER BY username')
    return [row[0] for row in cur.fetchall()]


def _pick_default_source(target_path):
    candidates = []
    patterns = [
        os.path.join(project_root, '3G_ERP_V1.db.backup_*'),
        os.path.join(project_root, 'instance', 'printing.db'),
        os.path.join(project_root, 'instance', 'printing.db.backup_*'),
    ]
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))

    ranked = []
    for path in sorted(set(candidates), reverse=True):
        if os.path.abspath(path) == os.path.abspath(target_path):
            continue
        if not os.path.exists(path):
            continue
        try:
            conn = sqlite3.connect(path)
            usernames = _admin_usernames(conn)
            columns = set(_admin_columns(conn))
            conn.close()
        except sqlite3.Error:
            continue
        if not usernames:
            continue
        score = len(usernames)
        if 'moderator_permissions' in columns and 'time_drift' in columns:
            score += 10
        if 'backup_' in os.path.basename(path):
            score += 5
        ranked.append((score, path, usernames))

    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def backup_database(db_path):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'{db_path}.backup_{timestamp}'
    shutil.copy2(db_path, backup_path)
    return backup_path


def restore_admin_rows(source_path, target_path, dry_run=False):
    source_conn = sqlite3.connect(source_path)
    target_conn = sqlite3.connect(target_path)

    source_cols = set(_admin_columns(source_conn))
    target_cols = set(_admin_columns(target_conn))
    shared_cols = [
        col for col in ADMIN_COPY_COLUMNS
        if col in source_cols and col in target_cols and col != 'id'
    ]
    if 'username' not in shared_cols:
        source_conn.close()
        target_conn.close()
        raise RuntimeError('Source database has no readable admin.username column')

    select_sql = f'SELECT {", ".join(shared_cols)} FROM admin ORDER BY id'
    source_rows = source_conn.execute(select_sql).fetchall()
    existing_usernames = set(_admin_usernames(target_conn))

    to_insert = []
    skipped = []
    for row in source_rows:
        row_data = dict(zip(shared_cols, row))
        username = row_data.get('username')
        if not username:
            continue
        if username in existing_usernames:
            skipped.append(username)
            continue
        to_insert.append(row_data)

    if dry_run:
        source_conn.close()
        target_conn.close()
        return {
            'inserted': [row['username'] for row in to_insert],
            'skipped': skipped,
            'backup_path': None,
        }

    if not to_insert and not skipped:
        source_conn.close()
        target_conn.close()
        return {'inserted': [], 'skipped': [], 'backup_path': None}

    backup_path = backup_database(target_path)
    placeholders = ', '.join(['?'] * len(shared_cols))
    insert_sql = (
        f'INSERT INTO admin ({", ".join(shared_cols)}) VALUES ({placeholders})'
    )

    try:
        for row_data in to_insert:
            values = [row_data[col] for col in shared_cols]
            target_conn.execute(insert_sql, values)
        target_conn.commit()
    except sqlite3.Error:
        target_conn.rollback()
        raise
    finally:
        source_conn.close()
        target_conn.close()

    return {
        'inserted': [row['username'] for row in to_insert],
        'skipped': skipped,
        'backup_path': backup_path,
    }


def verify_with_orm():
    with app.app_context():
        admins = Admin.query.order_by(Admin.id).all()
        return [
            {
                'id': admin.id,
                'username': admin.username,
                'role': admin.role,
                'email': admin.email,
                'two_fa_enabled': admin.two_fa_enabled,
            }
            for admin in admins
        ]


def main():
    parser = argparse.ArgumentParser(description='Restore admin users from backup DB')
    parser.add_argument(
        '--source',
        help='Backup database path (default: auto-pick best candidate)',
    )
    parser.add_argument(
        '--target',
        help='Target database path (default: app DATABASE_FILE)',
    )
    parser.add_argument('--dry-run', action='store_true', help='Show actions without writing')
    args = parser.parse_args()

    with app.app_context():
        target_path = os.path.abspath(args.target or app.config['DATABASE_FILE'])

    if not os.path.exists(target_path):
        print(f'ERROR: Target database not found: {target_path}')
        return 1

    source_path = args.source
    if source_path:
        source_path = os.path.abspath(source_path)
    else:
        source_path = _pick_default_source(target_path)

    if not source_path or not os.path.exists(source_path):
        print('ERROR: No backup source with admin users found.')
        print('Pass --source explicitly, e.g.:')
        print('  python scripts/restore_admin_from_backup.py --source 3G_ERP_V1.db.backup_20260630_143423')
        return 1

    print('=== Admin restore ===')
    print(f'Target: {target_path}')
    print(f'Source: {source_path}')
    print(f'Dry run: {args.dry_run}')
    print()

    before = verify_with_orm()
    print(f'Before restore: {len(before)} admin(s)')
    for row in before:
        print(f"  - {row['username']} ({row['role']})")

    result = restore_admin_rows(source_path, target_path, dry_run=args.dry_run)

    print()
    if result['backup_path']:
        print(f'Pre-restore backup created: {result["backup_path"]}')
    if result['inserted']:
        print('Inserted users:', ', '.join(result['inserted']))
    else:
        print('Inserted users: (none)')
    if result['skipped']:
        print('Skipped existing users:', ', '.join(result['skipped']))

    if args.dry_run:
        print('\nDry run complete. Re-run without --dry-run to apply changes.')
        return 0

    after = verify_with_orm()
    print()
    print(f'After restore: {len(after)} admin(s)')
    for row in after:
        print(
            f"  - id={row['id']} username={row['username']} role={row['role']} "
            f"email={row['email']} 2fa={row['two_fa_enabled']}"
        )

    if not after:
        print('WARNING: Admin.query still returns no users.')
        return 1

    print('\nRestore complete. Log in with your original password from the backup source.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
