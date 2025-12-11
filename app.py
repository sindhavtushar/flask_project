import secrets
from flask import Flask, flash, render_template, request, redirect, url_for, session, g

# from db_manager_1 import TimesheetDB
from db_manager import TimesheetDB


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
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        db = get_db_conn()
        # success, msg = db.register_user(username, password, role)
        success, msg = db.register_user(username, email, password, role)

        if success:
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login_user'))

        # If registration fails
        flash(f'Registration failed: {msg}', 'danger')
        # return render_template('registerpage.html', username=username, role=role,)
        return render_template('registerpage.html', email=email, role=role,)

    # for GET request
    # return render_template('registerpage.html', username='', role='')
    return render_template('registerpage.html', email='', role='')

@app.route('/login', methods=['GET', 'POST'])
def login_user():
    if 'user_id' in session:
        return redirect(url_for('dashboard_view'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        db = get_db_conn()
        # Login by email and password
        data = db.login_user(email, password)

        if data:
            user_id, role = data
            session['user_id'] = user_id
            session['user_role'] = role
            session['email'] = email

            # Fetch username from database
            row = db.cursor.execute(
                "SELECT username FROM user WHERE user_id = ?", (user_id,)
            ).fetchone()
            session['username'] = row['username'] if row else ""

            return redirect(url_for('dashboard_view'))

        # Login failed
        flash('Invalid email or password.', 'danger')
        return render_template('loginpage.html', email=email)  # keep email input

    # GET request
    return render_template('loginpage.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard_view():
    # Authentication Check
    if 'user_id' not in session:
        flash("Please login first!", 'danger')
        return redirect(url_for('login_user'))

    user_id = session['user_id']
    user_role = session['user_role']
    db = get_db_conn()

    # Handle New Log Entry (Normal User)
    if request.method == 'POST' and 'date' in request.form and 'user_id' not in request.form:
        date = request.form.get('date')
        clock_in = request.form.get('clock_in')
        clock_out = request.form.get('clock_out')
        task_description = request.form.get('task_description')
    
        result = db.add_log(user_id, clock_in, clock_out, date, task_description)

        if result == "success":
            flash("Log added successfully!", 'success')
        elif result == "duplicate":
            flash("A log for this date already exists!", 'warning')
        else:
            flash("Error adding log. Check date/time format.", 'danger')

        return redirect(url_for('dashboard_view'))

    # Fetch Personal Logs
    personal_logs = db.get_logs(user_id=user_id, role='user')

    # Senior Role Handling
    users_list = []
    target_user_logs = []
    target_username = ''

    if user_role == 'senior':
        users_list = db.cursor.execute(
            "SELECT user_id, username FROM user WHERE role='user'"
        ).fetchall()

        if request.method == 'POST' and 'user_id' in request.form:
            try:
                target_user_id = int(request.form['user_id'])
                # Fetch logs of selected junior
                target_user_logs = db.get_logs(user_id=target_user_id, role='user')
                
                row = db.cursor.execute(
                    "SELECT username FROM user WHERE user_id = ?", (target_user_id,)
                ).fetchone()
                if row:
                    target_username = row['username']
            except ValueError:
                flash("Invalid user selection.", 'danger')

    # Fetch current logged-in username from DB
    row = db.cursor.execute(
        "SELECT username FROM user WHERE user_id = ?", (user_id,)
    ).fetchone()
    current_username = row['username'] if row else ''

    # Render Template
    return render_template(
        'dashboard.html',
        user={'username': current_username},
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
    message = db.delete_log(log_id, session['user_id'], session['user_role'])
    if message:
        flash("Log deleted successfully!", 'success')
        return redirect(url_for('dashboard_view'))
    else:
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
        flash("Log not found!", 'danger')
        return redirect(url_for('dashboard_view'))

    if log['user_id'] != session['user_id'] and session.get('user_role') != 'senior':
        flash("Unauthorized access!", 'danger')
        return redirect(url_for('dashboard_view'))

    # Update
    result = db.update_log(log_id, session['user_id'], clock_in, clock_out, date, task_description, session['user_role'])
    # (self, log_id, user_id, clock_in, clock_out, date, task_description, role):
    if result == "success":
        flash("Log updated successfully!", 'success')
    elif result == "duplicate":
        flash("A log for this date already exists!", 'warning')
    else:
        flash("Error updating log. Check date/time format.", 'danger')

    return redirect(url_for('dashboard_view'))

@app.route('/logout', methods=['GET', 'POST'])
def logout_user():
    session.pop('user_id', None)
    session.pop('user_role', None)
    session.pop('username', None)
    flash('Logout successfully!', 'success')
    return redirect(url_for('home'))

# -------- RUN SERVER --------
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
