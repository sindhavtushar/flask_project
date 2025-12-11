from datetime import datetime, timedelta
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

class TimesheetDB:

    def __init__(self, db_name='log_tracking_1.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False, timeout=5)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()

        self.create_tables()
        # self.prepopulate_admins()

    # TABLE CREATION
    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS user(
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS timesheet(
                SNO INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                clock_in TEXT NOT NULL,
                clock_out TEXT NOT NULL,
                workhour TEXT NOT NULL DEFAULT '00:00',
                date DATE NOT NULL,
                task_description TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES user(user_id),
                UNIQUE(user_id, date)   -- FIXED (unique per user per date)
            );
        """)

        self.conn.commit()

    # # PREDEFINED ADMINS
    # def prepopulate_admins(self):
    #     predefined_users = [
    #         ('CEO','ceo@xyzorg.ac.in','ceo123', 'ceo')   # FIXED: role was 'senior'
    #     ]
    #     for username, password, role in predefined_users:
    #         self.cursor.execute("SELECT user_id FROM user WHERE username = ?", (username,))
    #         if not self.cursor.fetchone():
    #             hashed_pw = generate_password_hash(password)
    #             self.cursor.execute("""
    #                 INSERT INTO user (username, password, role)
    #                 VALUES (?, ?, ?)
    #             """, (username, hashed_pw, role))

        self.conn.commit()

    # USER OPERATIONS
    def register_user(self, username, email, password, role="user"):
        self.cursor.execute("SELECT user_id FROM user WHERE email = ?", (email,))
        if self.cursor.fetchone():
            return False, "Email already exists"

        hashed_pw = generate_password_hash(password)
        self.cursor.execute(
            "INSERT INTO user (username, email, password, role) VALUES (?, ?, ?, ?)",
            (username, email, hashed_pw, role)
        )
        self.conn.commit()
        return True, "User registered successfully"

    def login_user(self, email, password):
        self.cursor.execute("SELECT * FROM user WHERE email = ?", (email,))
        record = self.cursor.fetchone()

        if record and check_password_hash(record['password'], password):
            return record['user_id'], record['role']
        return None

    # WORK HOUR CALCULATION (shared)
    def calculate_work_hours(self, date_str, clock_in_str, clock_out_str):
        try:
            TIME_FORMAT = "%H:%M"
            DATE_FORMAT = "%Y-%m-%d"

            dt_in = datetime.strptime(f"{date_str} {clock_in_str}", f"{DATE_FORMAT} {TIME_FORMAT}")
            dt_out = datetime.strptime(f"{date_str} {clock_out_str}", f"{DATE_FORMAT} {TIME_FORMAT}")

            # Overnight shift
            if dt_out < dt_in:
                dt_out += timedelta(days=1)

            total_duration = dt_out - dt_in
            BREAK_DURATION = timedelta(hours=1)

            # Prevent negative time
            work_duration = max(total_duration - BREAK_DURATION, timedelta())

            total_seconds = int(work_duration.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60

            return f"{hours:02d}:{minutes:02d}"

        except ValueError:
            return None

    # TIMESHEET ADD
    def add_log(self, user_id, clock_in_str, clock_out_str, date_str, task_description):
        work_hours_str = self.calculate_work_hours(date_str, clock_in_str, clock_out_str)
        if work_hours_str is None:
            return "format_error"

        # Check duplicate entry for same user same date
        self.cursor.execute(
            "SELECT 1 FROM timesheet WHERE user_id = ? AND date = ?",
            (user_id, date_str)
        )
        if self.cursor.fetchone():
            return "duplicate"

        self.cursor.execute("""
            INSERT INTO timesheet (user_id, clock_in, clock_out, workhour, date, task_description)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, clock_in_str, clock_out_str, work_hours_str, date_str, task_description))

        self.conn.commit()
        return "success"

    # GET LOGS
    def get_logs(self, user_id=None, role="user", target_user_id=None):
        base_query = """
            SELECT t.SNO, t.user_id, u.username,
                t.clock_in, t.clock_out, t.workhour,
                t.date, t.task_description
            FROM timesheet t
            JOIN user u ON t.user_id = u.user_id
        """

        if role == "ceo":
            query = base_query
            params = ()

        elif role == "senior":
            if target_user_id:
                query = base_query + " WHERE t.user_id = ?"
                params = (target_user_id,)
            else:
                query = base_query + " WHERE u.role = 'user'"
                params = ()

        else:
            query = base_query + " WHERE t.user_id = ?"
            params = (user_id,)

        self.cursor.execute(query, params)
        return [dict(row) for row in self.cursor.fetchall()]

    # DELETE LOG (CEO & Senior can delete anyone's)
    def delete_log(self, log_id, user_id, role):
        try:
            if role in ("ceo", "senior"):
                self.cursor.execute("DELETE FROM timesheet WHERE SNO = ?", (log_id,))
            else:
                self.cursor.execute("DELETE FROM timesheet WHERE SNO = ? AND user_id = ?", (log_id, user_id))

            self.conn.commit()
            return True
        except Exception as e:
            return f"error: {e}"

    # GET LOG BY ID
    def get_log_by_id(self, sno):
        self.cursor.execute("SELECT * FROM timesheet WHERE SNO = ?", (sno,))
        row = self.cursor.fetchone()
        return dict(row) if row else None

    # UPDATE LOG
    def update_log(self, log_id, user_id, clock_in, clock_out, date, task_description, role):
        work_hours_str = self.calculate_work_hours(date, clock_in, clock_out)
        if work_hours_str is None:
            return "format_error"

        # Check duplicate date (fix id → SNO)
        self.cursor.execute(
            "SELECT 1 FROM timesheet WHERE user_id = ? AND date = ? AND SNO != ?",
            (user_id, date, log_id)
        )
        if self.cursor.fetchone():
            return "duplicate"

        # Allow admins to update any user's logs
        if role in ("ceo", "senior"):
            update_query = """
                UPDATE timesheet
                SET clock_in = ?, clock_out = ?, workhour = ?, date = ?, task_description = ?
                WHERE SNO = ?
            """
            params = (clock_in, clock_out, work_hours_str, date, task_description, log_id)

        else:
            update_query = """
                UPDATE timesheet
                SET clock_in = ?, clock_out = ?, workhour = ?, date = ?, task_description = ?
                WHERE SNO = ? AND user_id = ?
            """
            params = (clock_in, clock_out, work_hours_str, date, task_description, log_id, user_id)

        self.cursor.execute(update_query, params)
        self.conn.commit()
        return "success"

    # CLEANUP
    def close(self):
        self.conn.close()
