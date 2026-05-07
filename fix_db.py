import sqlite3
import os

def fix_database():
    # 1. Find the database file
    db_path = os.path.join('instance', 'database.db')
    if not os.path.exists(db_path):
        # Try current directory if instance folder isn't found
        db_path = 'database.db'
    
    print(f"Connecting to: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 2. Identify the correct table name (Order vs order)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"Tables found in database: {tables}")

    target_table = None
    if 'order' in tables:
        target_table = 'order'
    elif 'Order' in tables:
        target_table = 'Order'

    if not target_table:
        print("Error: Could not find an 'Order' table. Please check your model name.")
        return

    # 3. Add the column
    try:
        print(f"Adding 'order_source' to table '{target_table}'...")
        # We use double quotes around the table name in case it's a reserved word
        cursor.execute(f'ALTER TABLE "{target_table}" ADD COLUMN order_source TEXT DEFAULT "Website"')
        conn.commit()
        print("Success! Column added.")
    except sqlite3.OperationalError as e:
        print(f"Note: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database()