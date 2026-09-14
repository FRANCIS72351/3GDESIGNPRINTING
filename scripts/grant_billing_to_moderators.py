"""Grant 'billing' permission to all moderator accounts that don't have it yet.

Run with the virtualenv active:
    python scripts/grant_billing_to_moderators.py
"""
from app import app, db
from models import Admin
import json

with app.app_context():
    mods = Admin.query.filter(Admin.role == 'moderator').all()
    updated = 0
    for m in mods:
        raw = m.moderator_permissions
        if not raw:
            perms = []
        else:
            try:
                perms = json.loads(raw)
                if not isinstance(perms, list):
                    perms = []
            except Exception:
                perms = []
        if 'billing' not in perms:
            perms.append('billing')
            m.moderator_permissions = json.dumps(perms)
            db.session.add(m)
            updated += 1
    if updated:
        db.session.commit()
    print(f"Processed {len(mods)} moderator accounts, updated {updated} to include 'billing'.")
