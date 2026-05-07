import sqlite3
import os

db_path = os.path.join(os.getcwd(), 'printing.db')
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(product_variant)")
    columns = cursor.fetchall()
    print("Table: product_variant")
    for col in columns:
        print(col)
    
    cursor.execute("PRAGMA table_info(admin)")
    columns = cursor.fetchall()
    print("\nTable: admin")
    for col in columns:
        print(col)
    conn.close()