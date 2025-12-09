import secrets
from flask import Flask, flash, render_template, request, redirect, url_for, session, g
from db_manager import TimesheetDB


def create_app():
    app = Flask(__name__)
    app.secret_key = secrets.token_hex()

    # ---------- DATABASE HANDLER ----------
    def get_db_conn():
        if 'db' not in g:
            g.db = TimesheetDB()
        return g.db

    @app.teardown_appcontext
    def close_db(exception):
        db = g.pop('db', None)
        if db is not None:
            db.close()

    # ---------- ROUTES ----------
    @app.route('/')
    def home():
        return render_template('home.html')

    @app.route('/register', methods=['GET', 'POST'])
    def register_user():
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']

            db = get_db_conn()
            success, msg = db.register_user(username, password)

            if success:
                return redirect(url_for('login_user'))
            return f'Registration failed: {msg}'

        return render_template('registerpage.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login_user():
        if 'user_id' in session:
            return redirect(url_for('dashboard_view'))

        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']

            db = get_db_conn()
            data = db.login_user(username, password)

            if data:
                user_id, role = data
                session['user_id'] = user_id
                session['user_role'] = role
                session['username'] = username
                return redirect(url_for('dashboard_view'))

            return "Invalid username or password!"

        return render_template('loginpage.html')

    @app.route('/dashboard', methods=['GET', 'POST'])
    def dashboard_view():
        if 'user_id' not in session:
            flash("Please login first!")
            return redirect(url_for('login_user'))

        user_id = session['user_id']
        user_role = session['user_role']
        db = get_db_conn()

        # ----- Handle new personal log entry -----
        if request.method == 'POST' and 'date' in request.form and 'user_id' not in request.form:
            date = request.form['date']
            clock_in = request.form['clock_in']
            clock_out = request.form['clock_out']
            task_description = request.form['task_description']

            db.add_log(user_id, clock_in, clock_out, date, task_description)
            flash("Log added successfully!")
            return redirect(url_for('dashboard_view'))

        # Fetch personal logs
        personal_logs = db.get_logs(user_id=user_id, role='user')

        # ----- Senior role handling -----
        users_list = []
        target_user_logs = []
        target_username = ''

        if user_role == 'senior':
            # fetch juniors
            users_list = db.cursor.execute(
                "SELECT user_id, username FROM user WHERE role='user'"
            ).fetchall()

            # senior selected a junior
            if request.method == 'POST' and 'user_id' in request.form:
                target_user_id = int(request.form['user_id'])
                target_user_logs = db.get_logs(
                    user_id=user_id,
                    role='senior',
                    target_user_id=target_user_id
                )
                target_username = db.cursor.execute(
                    "SELECT username FROM user WHERE user_id = ?",
                    (target_user_id,)
                ).fetchone()['username']

        return render_template(
            'dashboard.html',
            user={'username': session['username']},
            user_role=user_role,
            logs=personal_logs,
            users=users_list,
            selected_user_logs=target_user_logs,
            selected_user_name=target_username
        )

    @app.route('/logs/delete/<int:log_id>', methods=['POST'])
    def delete_log(log_id):
        if 'user_id' not in session:
            return redirect(url_for('login_user'))

        db = get_db_conn()
        db.cursor.execute(
            "DELETE FROM timesheet WHERE SNO = ? AND user_id = ?",
            (log_id, session['user_id'])
        )
        db.conn.commit()

        return redirect(url_for('dashboard_view'))

    @app.route('/logs/update/<int:log_id>', methods=['POST'])
    def update_log(log_id):
        if 'user_id' not in session:
            return redirect(url_for('login_user'))

        # Safer field access
        date = request.form.get('date', '')
        clock_in = request.form.get('clock_in', '')
        clock_out = request.form.get('clock_out', '')
        task_description = request.form.get('task_description', '')

        db = get_db_conn()

        # Authorization check
        log = db.get_log_by_id(log_id)
        if not log:
            flash("Log not found!")
            return redirect(url_for('dashboard_view'))

        if log['user_id'] != session['user_id'] and session.get('user_role') != 'senior':
            flash("Unauthorized access!")
            return redirect(url_for('dashboard_view'))

        # Update
        db.update_log(log_id, clock_in, clock_out, date, task_description)

        flash("Log updated successfully!")
        return redirect(url_for('dashboard_view'))


    @app.route('/logout', methods=['GET', 'POST'])
    def logout_user():
        session.pop('user_id', None)
        session.pop('user_role', None)
        session.pop('username', None)
        return redirect(url_for('home'))

    return app


# -------- RUN SERVER --------
if __name__ == '__main__':
    app_instance = create_app()
    app_instance.run()
    
    # app_instance.run(debug=True, host='0.0.0.0', port=5000)
