from app import app, db

with app.app_context():
    print("Creating all database tables...")
    db.create_all()
    print("Done! If the tables already existed, nothing was changed.")
    
    # Let's double check if 'Order' is there now
    from sqlalchemy import inspect
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"Tables now in database: {tables}")