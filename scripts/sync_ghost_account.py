#!/usr/bin/env python3
"""Align the ghost recovery account with GHOST_ADMIN_USER and backup credentials."""
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
from models import Admin, db  # noqa: E402

GHOST_EMAIL = 'ghost@system.local'
ADMIN_COPY_COLUMNS = [
    'username',
    'password_hash',
    'email',
    'role',
    'moderator_permissions',
    'otp_secret',
    'recovery_key',
    'two_fa_enabled',
    'failed_2fa_count',
    'time_drift',
]


def _pick_backup_source(ghost_username):
    patterns = [
        os.path.join(project_root, '3G_ERP_V1.db.backup_*'),
        os.path.join(project_root, 'instance', 'printing.db'),
    ]
    candidates = []
    for pattern in patterns:
        candidates.extend(glob.glob(pattern))

    ranked = []
    for path in sorted(set(candidates), reverse=True):
        try:
            conn = sqlite3.connect(path)
            row = conn.execute(
                'SELECT username FROM admin WHERE username = ? OR email = ?',
                (ghost_username, GHOST_EMAIL),
            ).fetchone()
            conn.close()
        except sqlite3.Error:
            continue
        if not row:
            continue
        score = 0
        if row[0] == ghost_username:
            score += 100
        if 'backup_202606' in path:
            score += 10
        ranked.append((score, path))

    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _ghost_row_from_backup(source_path, ghost_username):
    conn = sqlite3.connect(source_path)
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(admin)')
    columns = {row[1] for row in cur.fetchall()}
    shared = [col for col in ADMIN_COPY_COLUMNS if col in columns]
    if not shared:
        conn.close()
        return None

    select_sql = f'SELECT {", ".join(shared)} FROM admin WHERE email = ? OR username = ?'
    row = conn.execute(select_sql, (GHOST_EMAIL, ghost_username)).fetchone()
    conn.close()
    if not row:
        return None
    return dict(zip(shared, row))


def backup_database(db_path):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'{db_path}.backup_{timestamp}'
    shutil.copy2(db_path, backup_path)
    return backup_path


def sync_ghost_account(source_path=None, dry_run=False):
    ghost_username = os.getenv('GHOST_ADMIN_USER', 'ghost_admin').strip() or 'ghost_admin'
    source_path = source_path or _pick_backup_source(ghost_username)

    with app.app_context():
        target_path = os.path.abspath(app.config['DATABASE_FILE'])
        ghost = Admin.query.filter_by(username=ghost_username).first()
        ghost_by_email = Admin.query.filter_by(email=GHOST_EMAIL).first()
        backup_row = _ghost_row_from_backup(source_path, ghost_username) if source_path else None

        actions = []
        if ghost and ghost_by_email and ghost.id != ghost_by_email.id:
            actions.append(
                f'WARNING: two ghost candidates found ({ghost.username}, {ghost_by_email.username})'
            )

        target = ghost or ghost_by_email
        if not target and backup_row:
            actions.append(f'create ghost account {ghost_username}')
        elif target:
            if target.username != ghost_username:
                actions.append(f'rename {target.username!r} -> {ghost_username!r}')
            if backup_row and backup_row.get('password_hash'):
                actions.append('restore ghost password_hash from backup')
        else:
            actions.append(f'no ghost account and no backup source ({source_path})')

        if dry_run:
            return {
                'ghost_username': ghost_username,
                'source': source_path,
                'actions': actions,
                'backup_path': None,
            }

        backup_path = backup_database(target_path) if actions else None

        if not target and backup_row:
            row = dict(backup_row)
            row['username'] = ghost_username
            row.setdefault('email', GHOST_EMAIL)
            row.setdefault('role', 'admin')
            target = Admin(**{k: v for k, v in row.items() if hasattr(Admin, k)})
            db.session.add(target)
        elif target:
            if target.username != ghost_username:
                target.username = ghost_username
            if backup_row:
                for col, value in backup_row.items():
                    if col == 'username':
                        continue
                    if value is not None and hasattr(target, col):
                        setattr(target, col, value)
            target.email = target.email or GHOST_EMAIL
            target.role = target.role or 'admin'

        if actions:
            db.session.commit()

        return {
            'ghost_username': ghost_username,
            'source': source_path,
            'actions': actions,
            'backup_path': backup_path,
            'usernames': [a.username for a in Admin.query.order_by(Admin.id).all()],
        }


def main():
    parser = argparse.ArgumentParser(description='Sync ghost recovery account with env + backup')
    parser.add_argument('--source', help='Backup database path')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    result = sync_ghost_account(source_path=args.source, dry_run=args.dry_run)
    print('=== Ghost account sync ===')
    print(f"GHOST_ADMIN_USER: {result['ghost_username']}")
    print(f"Source: {result['source']}")
    for action in result['actions']:
        print(f'  - {action}')
    if result.get('backup_path'):
        print(f"Backup: {result['backup_path']}")
    if result.get('usernames'):
        print('Admin usernames:', ', '.join(result['usernames']))
    if args.dry_run:
        print('\nDry run only. Re-run without --dry-run to apply.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
