from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        try:
            # Add the missing email column to the leaders table
            conn.execute(text("ALTER TABLE leaders ADD COLUMN email VARCHAR(120)"))
            conn.commit()
            print("Leader email column added successfully!")
        except Exception as e:
            print(f"Error: {e}")