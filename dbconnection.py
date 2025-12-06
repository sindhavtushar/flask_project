# dbconnection.py

import sqlite3
from flask import g, current_app 

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        # Get the database path from the configuration dictionary set in app.py
        db_path = current_app.config.get('DATABASE')
        if db_path is None:
            raise ValueError("DATABASE configuration not set in app.py")
        db = g._database = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")

    return db

# We attach this function to the app instance in a separate setup function below
def close_connection(exception=None):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    # Use current_app.app_context() instead of app.app_context()
    with current_app.app_context():
        try:
            db = get_db()
            cursor = db.cursor()

            # Create the 'user' table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                );
            """)
            # Create the 'timesheet' tables
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS timesheet (
                    SNO INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL, 
                    clockIn TIME NOT NULL,
                    clockOut TIME NOT NULL,
                    date DATE NOT NULL,
                    tasks TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)


            db.commit()

            print("Table 'users' and 'timesheet' created successfully!")

        except sqlite3.Error as e:
            current_app.logger.error(f'Error creating tables: {e}')
        finally:
            # don't call close_connection() manually here, the teardown context will handle it
            pass 

# Define a function to register the teardown with the app instance in app.py
def init_app_db(app):
    """Register the database connection closing function with the Flask app."""
    app.teardown_appcontext(close_connection)
