from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        try:
            # Adding both email and contact to leaders just in case
            conn.execute(text("ALTER TABLE leaders ADD COLUMN email VARCHAR(120)"))
            conn.execute(text("ALTER TABLE leaders ADD COLUMN contact VARCHAR(20)"))
            
            # Ensure the sale table also has the sms status
            conn.execute(text("ALTER TABLE sale ADD COLUMN sms_status VARCHAR(20) DEFAULT 'Pending'"))
            
            conn.commit()
            print("3G DESIGN Database is now fully updated!")
        except Exception as e:
            print(f"Note: Some columns might already exist. Error: {e}")