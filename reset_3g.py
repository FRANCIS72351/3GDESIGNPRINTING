import os
from app import app, db

def reset_database():
    with app.app_context():
        # 1. Find the database path
        db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        
        # 2. Delete the file if it exists to clear the 'no such column' errors
        if os.path.exists(db_path):
            print(f"Removing old database at: {db_path}")
            os.remove(db_path)
        
        # 3. Create everything fresh with the new columns (contact, email, sms_status, etc.)
        print("Building fresh 3G DESIGN database...")
        db.create_all()
        print("Success! All columns (contact, email, stock_quantity) are now created.")

if __name__ == "__main__":
    reset_database()