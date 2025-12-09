import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash


class TimesheetDB:
    def __init__(self, db_name='log_tracking.db'):
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Return rows as dict-like objects
        self.cursor = self.conn.cursor()

        self.create_tables()
        self.prepopulate_admins()

    # TABLE CREATION
    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS user(
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
            );
        """)

        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS timesheet(
                SNO INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                clock_in TIME NOT NULL,
                clock_out TIME NOT NULL,
                date DATE NOT NULL,
                task_description TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES user(user_id)
            );
        """)

        self.conn.commit()

    # PREDEFINED ADMINS / SENIORS
    def prepopulate_admins(self):
        predefined_users = [
            ('maitri koyani', 'sen123', 'senior'),
            ('darshit hirani', 'sen234', 'senior'),
            ('ceo1', 'ceo123', 'ceo')
        ]

        for username, password, role in predefined_users:
            self.cursor.execute("SELECT user_id FROM user WHERE username = ?", (username,))
            if not self.cursor.fetchone():
                hashed_pw = generate_password_hash(password)
                self.cursor.execute(
                    "INSERT INTO user (username, password, role) VALUES (?, ?, ?)",
                    (username, hashed_pw, role)
                )

        self.conn.commit()

    # USER OPERATIONS
    def register_user(self, username, password):
        self.cursor.execute("SELECT user_id FROM user WHERE username = ?", (username,))
        if self.cursor.fetchone():
            return False, "Username already exists"

        hashed_pw = generate_password_hash(password)
        self.cursor.execute(
            "INSERT INTO user (username, password) VALUES (?, ?)",
            (username, hashed_pw)
        )
        self.conn.commit()

        return True, "User registered successfully"

    def login_user(self, username, password):
        self.cursor.execute("SELECT * FROM user WHERE username = ?", (username,))
        record = self.cursor.fetchone()

        if record and check_password_hash(record['password'], password):
            return record['user_id'], record['role']

        return None

    # ----------------------------------------
    # TIMESHEET OPERATIONS
    # ----------------------------------------
    
    def add_log(self, user_id, clock_in, clock_out, date, task_description):
        self.cursor.execute("""
            INSERT INTO timesheet (user_id, clock_in, clock_out, date, task_description)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, clock_in, clock_out, date, task_description))

        self.conn.commit()

    
    def get_logs(self, user_id=None, role='user', target_user_id=None):
        base_query = """
            SELECT t.SNO, t.user_id, u.username, 
                   t.clock_in, t.clock_out, t.date, t.task_description
            FROM timesheet t
            JOIN user u ON t.user_id = u.user_id
        """

        if role == 'ceo':
            self.cursor.execute(base_query)

        elif role == 'senior':
            if target_user_id:
                self.cursor.execute(
                    base_query + " WHERE u.user_id = ?",
                    (target_user_id,)
                )
            else:
                self.cursor.execute(
                    base_query + " WHERE u.role = 'user' OR u.user_id = ?",
                    (user_id,)
                )

        else:
            # Normal user — only own logs
            self.cursor.execute(
                base_query + " WHERE u.user_id = ?",
                (user_id,)
            )

        return [dict(row) for row in self.cursor.fetchall()]

    def update_log(self, sno, clock_in, clock_out, date, task_description):
        self.cursor.execute("""
            UPDATE timesheet
            SET clock_in = ?, clock_out = ?, date = ?, task_description = ?
            WHERE SNO = ?
        """, (clock_in, clock_out, date, task_description, sno))

        self.conn.commit()

    def get_log_by_id(self, sno):
        self.cursor.execute("SELECT * FROM timesheet WHERE SNO = ?", (sno,))
        row = self.cursor.fetchone()
        if row:
            # Convert row to dictionary for easier access
            return {
                'SNO': row[0],
                'user_id': row[1],
                'clock_in': row[2],
                'clock_out': row[3],
                'date': row[4],
                'task_description': row[5]
            }
        return None


    # CLEANUP
    def close(self):
        self.conn.close()

