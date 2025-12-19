import psycopg2
from psycopg2.extras import RealDictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
from datetime import datetime, timedelta

class DatabaseManager:

    def __init__(
        self,
        host="localhost",
        dbname="log_tracker",
        user="postgres",
        password="pyp123",
        port=5432
    ):
        self.conn = psycopg2.connect(
            host=host,
            dbname=dbname,
            user=user,
            password=password,
            port=port
        )
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)

   
    # USER HELPERS
   
    def email_exists(self, email):
        self.cursor.execute("SELECT 1 FROM users WHERE email = %s", (email,))
        return self.cursor.fetchone() is not None

    def get_user_by_email(self, email):
        self.cursor.execute("""
            SELECT id, username, email
            FROM users
            WHERE email = %s
        """, (email,))
        return self.cursor.fetchone()

    def get_user_id(self, email):
        self.cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        row = self.cursor.fetchone()
        return row['id'] if row else None

    def is_verified(self, email):
        self.cursor.execute("SELECT is_verified FROM users WHERE email = %s", (email,))
        row = self.cursor.fetchone()
        return row['is_verified'] if row else None

    def insert_user(self, username, email, password, role='user'):
        hashed_pw = generate_password_hash(password)
        try:
            self.cursor.execute("""
                INSERT INTO users (username, email, password_hash, role)
                VALUES (%s, %s, %s, %s)
                RETURNING id, username, email, role, is_verified
            """, (username, email, hashed_pw, role))
            self.conn.commit()
            return self.cursor.fetchone()
        except psycopg2.errors.UniqueViolation:
            self.conn.rollback()
            return None

    def get_users_by_role(self, role, requester_role):
        """
        Fetch users filtered by role, only if requester is admin or senior.
        
        :param role: Role to filter ('admin', 'senior', 'user')
        :param requester_role: Role of the user making the request
        :return: List of users matching the role
        """
        if requester_role not in ('admin', 'senior'):
            return []  # Only admin or senior can fetch users

        self.cursor.execute("""
            SELECT id, username, email, role, is_verified, created_at
            FROM users
            WHERE role = %s
            ORDER BY username
        """, (role,))
        
        return self.cursor.fetchall()

    def mark_user_verified(self, user_id):
            """
            Mark a user as verified.
            """
            try:
                query = "UPDATE users SET is_verified = TRUE WHERE id = %s"
                self.cursor.execute(query, (user_id,))
                self.conn.commit()
                return True
            except Exception as e:
                self.conn.rollback()
                print(f"[DB ERROR] mark_user_verified: {e}")
                return False

    def register_user(self, username, email, password):
        if self.email_exists(email):
            return False, "Email already registered"

        user = self.insert_user(username, email, password)
        if user:
            return True, user
        return False, "Registration failed"

    def login_user(self, email, password):
        self.cursor.execute("""
            SELECT id, username, email, password_hash, role, is_verified
            FROM users
            WHERE email = %s
        """, (email,))
        user = self.cursor.fetchone()
        if not user:
            return False, "User not found"
        if not user["is_verified"]:
            return False, "Account not verified"
        if not check_password_hash(user["password_hash"], password):
            return False, "Invalid password"
        return True, {
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"]
        }

    # def update_user_password(self, email, password):
    #     hashed_password = generate_password_hash(password)
    #     try:
    #         self.cursor.execute("""
    #             UPDATE users
    #                 SET password_hash = %s
    #                 WHERE email = %s;
    #         """, (hashed_password, email, ))
    #         message = 'Password Updated'
    #         return True, message
    #     except psycopg2.Error as e:
    #         # Catch all other psycopg2 errors
    #         return False, f"A general database error occurred: {e}"
    #     except Exception as e:
    #         # Catch any other Python exceptions
    #         return False, f"An unexpected error occurred: {e}"

    def update_user_password(self, email, password):
        hashed_password = generate_password_hash(password)

        try:
            self.cursor.execute("""
                UPDATE users
                SET password_hash = %s
                WHERE email = %s;
            """, (hashed_password, email))

            self.conn.commit()  # ✅ VERY IMPORTANT

            if self.cursor.rowcount == 0:
                return False, "User not found"

            return True, "Password updated successfully"

        except psycopg2.Error as e:
            self.conn.rollback()
            return False, f"Database error: {e}"

        except Exception as e:
            self.conn.rollback()
            return False, f"Unexpected error: {e}"


    # OTP HELPERS
   
    def generate_otp(self, user_id, purpose='verify_email', expiry_minutes=10):
        # otp = ''.join(random.choices(string.digits, k=6))
        # otp_hash = generate_password_hash(otp)

        otp = str(random.randint(100000, 999999))
        otp_hash = generate_password_hash(otp)

        expires_at = datetime.now() + timedelta(minutes=expiry_minutes)

        self.cursor.execute("""
            INSERT INTO user_otp (user_id, otp_hash, purpose, expires_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (user_id, otp_hash, purpose, expires_at))
        self.conn.commit()
        return otp  # Send this to user via email/SMS

    def verify_otp(self, user_id, input_otp, purpose='verify_email'):
        input_otp = str(input_otp).strip()
        self.cursor.execute("""
            SELECT id, otp_hash, expires_at, is_used
            FROM user_otp
            WHERE user_id = %s AND purpose = %s AND is_used = FALSE
            ORDER BY created_at DESC
            LIMIT 1
        """, (user_id, purpose))
        row = self.cursor.fetchone()
        if not row:
            return False, "No OTP found"
        if datetime.now() > row['expires_at']:
            return False, "OTP expired"
        if not check_password_hash(row['otp_hash'], input_otp):
            return False, "Invalid OTP"

        # Mark OTP used
        self.cursor.execute("UPDATE user_otp SET is_used = TRUE WHERE id = %s", (row['id'],))
        self.conn.commit()
        if purpose == 'verify_email':
            self.cursor.execute(
                "UPDATE users SET is_verified = TRUE WHERE id = %s",
                (user_id,)
            )
            self.conn.commit()
        return True, "OTP verified"

   
    # ADMIN / SENIOR HELPERS
   
    def create_admin(self, username, email, password):
        return self.insert_user(username, email, password, role='admin')

    def create_senior(self, username, email, password):
        return self.insert_user(username, email, password, role='senior')

    def list_users(self, requester_role):
        if requester_role not in ('admin', 'senior'):
            return []
        self.cursor.execute("""
            SELECT id, username, email, role, is_verified, created_at
            FROM users
            ORDER BY role DESC, username
        """)
        return self.cursor.fetchall()
   
    # TIMESHEET / LOG HELPERS

    def get_logs(self, user_id):
        self.cursor.execute("""
            SELECT id, clock_in, clock_out, work_date, task_description, work_duration
            FROM timesheet
            WHERE user_id = %s
            ORDER BY work_date DESC
        """, (user_id,))
            
        logs = self.cursor.fetchall()
        logs_with_hours = []

        for log in logs:
            # Format time
            log['clock_in'] = log['clock_in'].strftime("%H:%M") if log['clock_in'] else ''
            log['clock_out'] = log['clock_out'].strftime("%H:%M") if log['clock_out'] else ''

            BREAK_HOURS = 1

            # Use DB duration directly
            if log['work_duration']:
                total_seconds = int(log['work_duration'].total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                log['workhour'] = f"{hours - BREAK_HOURS}h {minutes}m"
            else:
                log['workhour'] = '0h 0m'

            # Format date
            log['work_date'] = log['work_date'].isoformat() if log['work_date'] else ''

            logs_with_hours.append(log)

        return logs_with_hours

    def get_log_by_id(self, log_id):
        self.cursor.execute("""
            SELECT id, clock_in, clock_out, work_date, task_description
            FROM timesheet
            WHERE id = %s
            ORDER BY work_date DESC
        """, (log_id,))
        logs = self.cursor.fetchall()
        return logs

    def add_log(self, user_id, clock_in, clock_out, work_date, task_description):
        try:
            # Accept both HH:MM and HH:MM:SS
            if len(clock_in) == 5:
                clock_in += ":00"
            if len(clock_out) == 5:
                clock_out += ":00"

            fmt = "%H:%M:%S"
            t_in = datetime.strptime(clock_in, fmt)
            t_out = datetime.strptime(clock_out, fmt)

            if t_out < t_in:
                t_out += timedelta(days=1)

            duration = t_out - t_in

            self.cursor.execute("""
                INSERT INTO timesheet
                (user_id, clock_in, clock_out, work_duration, work_date, task_description)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, clock_in, clock_out, duration, work_date, task_description))

            self.conn.commit()
            return "success"

        except psycopg2.errors.UniqueViolation:
            self.conn.rollback()
            return "duplicate"

        except Exception as e:
            self.conn.rollback()
            print("Add log error:", e)
            return "error"

    def delete_log(self, log_id, user_id, user_role):
        try:
            if user_role == 'admin':
                # Admin can delete any log
                self.cursor.execute("""
                    DELETE FROM timesheet
                    WHERE id = %s
                    RETURNING id
                """, (log_id,))
            else:
                # Normal user can delete only their own logs
                self.cursor.execute("""
                    DELETE FROM timesheet
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                """, (log_id, user_id))

            deleted = self.cursor.fetchone()
            self.conn.commit()

            if deleted:
                return True
            else:
                return False

        except Exception as e:
            self.conn.rollback()
            print("Delete error:", e)  # optional logging
            return False

    def update_log(self, log_id, user_id, clock_in, clock_out, work_date, task_description, requester_role):
        """
        Update a timesheet log.
        - Normal user can update only their own log
        - Senior/Admin can update any log
        - Returns:
            "success"  -> updated
            "duplicate" -> same user already has log for this date
            "error"    -> any other error
        """
        try:
            # Convert clock_in/out to time objects if string
            if isinstance(clock_in, str):
                if len(clock_in) == 5:  # HH:MM
                    clock_in += ":00"
                clock_in = datetime.strptime(clock_in, "%H:%M:%S").time()

            if isinstance(clock_out, str):
                if len(clock_out) == 5:
                    clock_out += ":00"
                clock_out = datetime.strptime(clock_out, "%H:%M:%S").time()

            # Calculate duration
            dt_in = datetime.combine(work_date, clock_in)
            dt_out = datetime.combine(work_date, clock_out)
            if dt_out < dt_in:
                dt_out += timedelta(days=1)  # handle overnight
            duration = dt_out - dt_in

            # Duplicate check for normal users
            if requester_role not in ['senior', 'admin']:
                self.cursor.execute("""
                    SELECT id FROM timesheet
                    WHERE user_id = %s AND work_date = %s AND id != %s
                """, (user_id, work_date, log_id))
                if self.cursor.fetchone():
                    return "duplicate"

            # Build UPDATE query
            if requester_role in ['senior', 'admin']:
                # Admin/senior can update any log
                self.cursor.execute("""
                    UPDATE timesheet
                    SET clock_in = %s,
                        clock_out = %s,
                        work_duration = %s,
                        work_date = %s,
                        task_description = %s
                    WHERE id = %s
                """, (clock_in, clock_out, duration, work_date, task_description, log_id))
            else:
                # Normal user can update only their own log
                self.cursor.execute("""
                    UPDATE timesheet
                    SET clock_in = %s,
                        clock_out = %s,
                        work_duration = %s,
                        work_date = %s,
                        task_description = %s
                    WHERE id = %s AND user_id = %s
                """, (clock_in, clock_out, duration, work_date, task_description, log_id, user_id))

            self.conn.commit()

            if self.cursor.rowcount == 0:
                return "error"  # nothing updated (unauthorized or not found)
            return "success"

        except Exception as e:
            self.conn.rollback()
            print("Update log error:", e)
            return "error"


# -----------------Testing-----------------------------

if __name__ == '__main__':

    test_email = 'tusharsindhav09@gmail.com'

    db = DatabaseManager()

    # print(db.get_user_by_email(test_email))
    logs = db.get_log_by_id(20)
    print(len(logs))
    print('content of logs:')
    cont = logs[0]
    for k, v in cont.items():
        print(k,':', v)

    print('user id:', logs[0]['id'])


    # print(db.add_log(3, '09:00:00', '17:00:00', '2025-12-09', 'record on date 9'))

    # print('----------log-----------:')
    # print(db.get_logs(3))

    # print('----------------------------------------')

    # result = db.delete_log(
    #     log_id=17,          # jo test record ka id hai
    #     user_id=3,         # same user
    #     user_role='user'   # normal user
    # )

    # print(result)
