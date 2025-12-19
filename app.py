from datetime import date, datetime, timedelta
from email.message import EmailMessage
import os
import smtplib
from flask import Flask, render_template, request, redirect, url_for, flash, session
from db import DatabaseManager

app = Flask(__name__)
app.secret_key = "secret"

#DB helper
def get_db():
    return DatabaseManager(
        host="localhost",
        dbname="log_tracker",   # MUST MATCH
        user="postgres",
        password="pyp123"
    )

# ------------------------------------------

# SMTP HANDLER
def send_email(to_email, message, subject):

    EMAIL_ADDRESS = os.getenv('SENDER_EMAIL')
    EMAIL_PASSWORD = os.getenv('SENDER_PASSWORD')

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = to_email
    
    msg.set_content(message)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
        smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        smtp.send_message(msg)
        print(f"OTP is send to {to_email}")

# -----------------------------------------------------------------------------------

@app.route('/')
def home():
    return render_template('home.html')

# ================= REGISTER =================

@app.route('/register', methods=['GET', 'POST'])
def register():
    db = DatabaseManager()
    message = None

    # Default to step 1
    step = session.get('step', 1)

    if request.method == 'POST':
        step = int(request.form.get('step', 1))

        if step == 1:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')

            if db.email_exists(email):
                verified = db.is_verified(email)
                if not verified:
                    user = db.get_user_by_email(email)
                    otp = db.generate_otp(user['id'], purpose='verify_email')
                    send_email(email, f"Your OTP is {otp}. It expires in 10 minutes.", "Email Verification OTP")
                    session['email'] = email
                    session['step'] = 2
                    flash('OTP sent to your registered email.', 'success')
                    return redirect(url_for('register'))
                else:
                    flash("User already registered and verified. Please login.", "info")
                    return redirect(url_for('login'))

            else:
                success, result = db.register_user(username, email, password)
                if success:
                    user = db.get_user_by_email(email)
                    otp = db.generate_otp(user['id'], purpose='verify_email')
                    send_email(email, f"Your OTP is {otp}. It expires in 10 minutes.", "User Registration OTP")
                    session['email'] = email
                    session['step'] = 2
                    flash('OTP sent to your registered email.', 'success')
                    return redirect(url_for('register'))
                else:
                    message = result

        elif step == 2:
            email = session.get('email')
            if not email:
                flash("Session expired. Please start again.", "danger")
                return redirect(url_for('register'))

            user = db.get_user_by_email(email)
            action = request.form.get('action', 'verify')

            if action == 'resend':
                otp = db.generate_otp(user['id'], purpose='verify_email')
                send_email(email, f"Your new OTP is {otp}", "Resend OTP")
                flash("OTP resent to your email.", "success")
                session['step'] = 2
                return redirect(url_for('register'))

            elif action == 'verify':
                input_otp = request.form.get('otp')
                is_verified, message = db.verify_otp(user['id'], input_otp, purpose='verify_email')
                if not is_verified:
                    flash(message, "danger")
                    session['step'] = 2
                    return redirect(url_for('register'))

                db.mark_user_verified(user['id'])
                session.pop('email', None)
                session.pop('step', None)
                flash("Email verified successfully. Please login.", "success")
                return redirect(url_for('login'))

    return render_template('register.html', step=step, message=message)


@app.route('/register/back')
def register_back():
    session['step'] = 1
    return redirect(url_for('register'))


# ================= LOGIN =================

@app.route('/login', methods=['GET', 'POST'])
def login():

    # # If already logged in
    # if 'user_id' in session:
    #     return redirect(url_for('dashboard'))

    db = get_db()
    step = session.get('step')  # None, forgot_email, forgot_otp, forgot_reset

    # -------------------- GET --------------------
    if request.method == 'GET':
        # User clicked "Forgot password?"
        if request.args.get('forgot') == '1':
            session['step'] = 'forgot_email'
            step = 'forgot_email'

        return render_template('login.html', step=step)

    # -------------------- POST --------------------

    # ========== NORMAL LOGIN ==========
    if step is None:
        email = request.form.get('email')
        password = request.form.get('password')

        success, result = db.login_user(email, password)

        if not success:
            flash(result, "danger")
            return render_template('login.html', step=None)

        # Login success
        session.clear()
        session['user_id'] = result['id']
        session['username'] = result['username']
        session['email'] = result['email']
        session['user_role'] = result['role']

        flash("Login successful 🎉", "success")
        return redirect(url_for('dashboard'))

    # ========== FORGOT PASSWORD : EMAIL ==========
    elif step == 'forgot_email':
        email = request.form.get('email')

        user = db.get_user_by_email(email)
        if not user:
            flash("Email not registered", "danger")
            return redirect(url_for('login'))

        # Save reset info
        session['reset_user_id'] = user['id']
        session['reset_email'] = user['email']

        otp = db.generate_otp(user['id'], purpose='reset_password')


        subject = "Password Reset OTP"
        message = f"Your OTP is {otp}. It expires in 10 minutes."
        send_email(email, message, subject)

        session['step'] = 'forgot_otp'
        flash("OTP sent to your email", "success")
        return redirect(url_for('login'))

    # ========== FORGOT PASSWORD : OTP ==========
    elif step == 'forgot_otp':
        user_otp = request.form.get('otp')

        user_id = session.get('reset_user_id')
        if not user_id:
            flash("Session expired. Please try again.", "danger")
            session.pop('step', None)
            return redirect(url_for('login'))


        is_verified, message = db.verify_otp(
            user_id=session['reset_user_id'],
            input_otp=user_otp,
            purpose='reset_password'
        )

        
        if not is_verified:
            flash(message, "danger")
            session['step'] = 'forgot_otp'
            return redirect(url_for('login'))


        session['step'] = 'forgot_reset'
        flash("OTP verified successfully", "success")
        return redirect(url_for('login'))

    # ========== FORGOT PASSWORD : RESET ==========
    elif step == 'forgot_reset':
        password = request.form.get('password')
        email = session.get('reset_email')

        success, message = db.update_user_password(email, password)

        # Clear reset session
        session.pop('reset_user_id', None)
        session.pop('reset_email', None)
        session.pop('step', None)

        flash("Password reset successful. Please login.", "success")
        return redirect(url_for('login'))



#------------Logour route----------
@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user_id', None)
    session.pop('user_role', None)
    session.pop('username', None)
    session.pop('email', None)
    flash('Logout successfully!', 'success')
    return redirect(url_for('home'))

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    
    # Authentication Check
    
    if 'user_id' not in session:
        flash("Please login first!", 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']
    user_role = session['user_role']
    db = DatabaseManager()

    
    # Handle New Log Entry (Normal User)
    if request.method == 'POST' and 'work_date' in request.form and 'user_id' not in request.form:

        work_date = datetime.strptime(request.form['work_date'], '%Y-%m-%d').date()
        today = date.today()  # Current date

        # Backend validation: future date check
        if work_date > today:
            flash("Future dates are not allowed!", 'danger')
            return redirect(url_for('dashboard'))

        clock_in = request.form.get('clock_in')
        clock_out = request.form.get('clock_out')
        task_description = request.form.get('task_description')

        result = db.add_log(user_id, clock_in, clock_out, work_date, task_description)

        if result == "success":
            flash("Log added successfully!", 'success')
        elif result == "duplicate":
            flash("A log for this date already exists!", 'warning')
        else:
            flash("Error adding log. Check date/time format.", 'danger')

        return redirect(url_for('dashboard'))


    # Fetch Personal Logs
    
    personal_logs = db.get_logs(user_id=user_id)

    # Senior / Admin Handling

    users_list = []
    target_user_logs = []
    target_username = None

    if user_role in ['senior', 'admin']:
        # Step 1: Fetch users list
        if user_role == 'admin':
            # Admin sees all users
            users_list = db.list_users(requester_role=user_role)
        else:
            # Senior sees only 'user' role
            users_list = db.get_users_by_role(requester_role=user_role, role='user')

        # Step 2: Handle selected user
        if request.method == 'POST' and 'user_id' in request.form:
            try:
                target_user_id = int(request.form['user_id'])

                # Step 2a: Fetch logs based on requester role
                if user_role == 'admin':
                    # Admin can see logs of all users
                    target_user_logs = db.get_logs(user_id=target_user_id)
                else:
                    # Senior can only see normal user logs
                    if any(u['id'] == target_user_id for u in users_list):
                        target_user_logs = db.get_logs(user_id=target_user_id)
                    else:
                        flash("You are not allowed to view this user's logs.", 'danger')
                        target_user_logs = []

                # Step 2b: Fetch selected username
                target_user = next((u for u in users_list if u['id'] == target_user_id), None)
                if target_user:
                    target_username = target_user['username']

            except ValueError:
                flash("Invalid user selection.", 'danger')


    # Fetch current logged-in username
    
    db.cursor.execute("SELECT username FROM users WHERE id = %s", (user_id,))
    row = db.cursor.fetchone()
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

# DELETE LOG (POST only)
@app.route('/logs/delete/<int:log_id>', methods=['POST'])
def delete_log(log_id):
    """
    Deletes a timesheet log.
    log_id: Maps directly to timesheet.id
    Authorization:
        - User can delete their own log
        - Senior/Admin can delete any log
    """
    if 'user_id' not in session:
        flash("Please login first!", 'danger')
        return redirect(url_for('login'))

    db = DatabaseManager()
    success = db.delete_log(log_id, session['user_id'], session['user_role'])

    if success:
        flash("Log deleted successfully!", 'success')
    else:
        flash("Unauthorized or log not found!", 'danger')

    return redirect(url_for('dashboard'))


# UPDATE LOG (POST only)
@app.route('/logs/update/<int:log_id>', methods=['POST'])
def update_log(log_id):
    if 'user_id' not in session:
        flash("Please login first!", 'danger')
        return redirect(url_for('login'))

    # Clean form data
    date_str = request.form.get('date', '').strip()
    clock_in = request.form.get('clock_in', '').strip()   # keep as "HH:MM"
    clock_out = request.form.get('clock_out', '').strip() # keep as "HH:MM"
    task_description = request.form.get('task_description', '').strip()

    # Convert date safely
    try:
        work_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Invalid date format!", 'danger')
        return redirect(url_for('dashboard'))

    db = DatabaseManager()
    log = db.get_log_by_id(log_id)
    if not log:
        flash("Log not found!", 'danger')
        return redirect(url_for('dashboard'))

    # Call DB update
    result = db.update_log(
        log_id,
        session['user_id'],         # log owner
        clock_in,             # string HH:MM
        clock_out,            # string HH:MM
        work_date,
        task_description,
        session['user_role']
    )

    # Handle response
    if result == "success":
        flash("Log updated successfully!", 'success')
    elif result == "duplicate":
        flash("A log for this date already exists!", 'warning')
    else:
        flash("Error updating log. Check date/time format.", 'danger')

    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port = 5000)
