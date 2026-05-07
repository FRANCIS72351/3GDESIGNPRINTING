from app import app, db
from sqlalchemy import text

with app.app_context():
    with db.engine.connect() as conn:
        # Add the missing columns manually
        try:
            conn.execute(text("ALTER TABLE product ADD COLUMN stock_quantity INTEGER DEFAULT 0"))
            conn.execute(text("ALTER TABLE product ADD COLUMN min_stock_threshold INTEGER DEFAULT 5"))
            conn.commit()
            print("Database patched successfully!")
        except Exception as e:
            print(f"Error patching: {e}")