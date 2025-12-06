# Application factory pattern
# app.py

import secrets
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, g
from werkzeug.security import generate_password_hash, check_password_hash

# from dbconnection import get_all_logs

# Define a function that creates and configures the application
def create_app():
    app = Flask(__name__)
    # Set the secret key and the database path in the config
    app.secret_key = secrets.token_hex()
    app.config['DATABASE'] = 'Log_Tracker.db'
    
    # Import the db setup function *inside* the factory function
    from dbconnection import init_app_db, get_db
    init_app_db(app) # Register the teardown handling

    # --- Routes ---

    @app.route('/')
    def index():
        return render_template('home.html')

    @app.route('/registerpage', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            hashed_password = generate_password_hash(password)

            db = get_db() # Use get_db() within the request context
            try:
                db.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                           (username, hashed_password))
                db.commit()
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                return "Username already exists!"
        return render_template('registerpage.html')

    @app.route('/loginpage', methods=['GET', 'POST'])
    def login():

        if 'user_id' in session:
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']

            db = get_db() # Use get_db() within the request context
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

            if user and check_password_hash(user['password'], password):
                session['user_id'] = user['user_id']
                return redirect(url_for('dashboard'))
            else:
                return "Invalid username or password"
        return render_template('loginpage.html')

    @app.route('/dashboard', methods=['GET', 'POST'])
    def dashboard():
        if 'user_id' not in session:
            return redirect(url_for('login'))

        db = get_db()
        db.row_factory = sqlite3.Row

        if request.method == 'POST':
            date = request.form.get('date')
            clockIn = request.form.get('clockIn')
            clockOut = request.form.get('clockOut')
            tasks = request.form.get('tasks')

            db.execute(
                "INSERT INTO timesheet (user_id, clockIn, clockOut, date, tasks) VALUES (?, ?, ?, ?, ?)",
                (session['user_id'], clockIn, clockOut, date, tasks)
            )
            db.commit()

            # IMPORTANT: prevent duplicate entries on refresh
            return redirect(url_for('dashboard'))

        logs = db.execute(
            "SELECT * FROM timesheet WHERE user_id = ?",
            (session['user_id'],)
        ).fetchall()

        user = db.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (session['user_id'],)
        ).fetchone()

        return render_template('dashboard.html', user=user, logs=logs)

    @app.route('/delete_log/<int:log_id>', methods=['POST'])
    def delete_log(log_id):
        if 'user_id' not in session:
            return redirect(url_for('login'))

        db = get_db()

        # Delete only if log belongs to the logged-in user
        db.execute(
            "DELETE FROM timesheet WHERE SNO = ? AND user_id = ?",
            (log_id, session['user_id'])
        )
        db.commit()

        return redirect(url_for('dashboard'))

    @app.route('/logout')
    def logout():
        session.pop('user_id', None)
        return redirect(url_for('index'))
    
    # Return the configured app instance
    return app

# --- Main execution block ---

if __name__ == '__main__':
    # 1. Create the application instance
    app_instance = create_app()

    # 2. To initialize the database schema *once* before running,
    # we use an application context manually.
    with app_instance.app_context():
        from dbconnection import init_db
        init_db() # Call init_db using the corrected dbconnection.py logic

    # 3. Run the application instance
    app_instance.run(debug=True, host='0.0.0.0', port=5000)
