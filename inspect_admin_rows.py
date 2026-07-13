import sqlite3
import os

files = [
    '3G_ERP_V1.db',
    'instance/database.db',
    'instance/printing.db',
    '3G_ERP_V1.db.backup_20260630_143423',
    'instance/printing.db.backup_20260413_142645',
]

for f in files:
    if not os.path.exists(f):
        print(f'FILE {f}: MISSING')
        continue
    try:
        conn = sqlite3.connect(f)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        if 'admin' in tables:
            cur.execute('SELECT username FROM admin')
            rows = cur.fetchall()
            print(f'FILE {f}: {rows}')
        else:
            print(f'FILE {f}: NO admin TABLE')
        conn.close()
    except Exception as e:
        print(f'FILE {f}: ERR {e}')
