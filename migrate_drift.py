from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        db.session.execute(text('ALTER TABLE admin ADD COLUMN time_drift INTEGER DEFAULT 0;'))
        db.session.commit()
        print("Migration Success: Added time_drift column.")
    except Exception as e:
        print(f"Migration Note: {e}")
