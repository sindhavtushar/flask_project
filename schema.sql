-- 1️ User role enum
CREATE TYPE user_role AS ENUM ('admin', 'senior', 'user');

-- 2️ OTP purpose enum
CREATE TYPE otp_purpose AS ENUM ('verify_email', 'reset_password');

-- 3️ Users table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'user',
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4️ Timesheet table
CREATE TABLE timesheet (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    clock_in TIME NOT NULL,
    clock_out TIME NOT NULL,
    work_duration INTERVAL NOT NULL DEFAULT '00:00',
    work_date DATE NOT NULL,
    task_description TEXT NOT NULL,
    UNIQUE (user_id, work_date)
);	

-- 5️ OTP table
CREATE TABLE user_otp (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    otp_hash TEXT NOT NULL,
    purpose otp_purpose NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);


-- updated password column because it causes problem in login due to hashed text is too long
ALTER TABLE users
ALTER COLUMN password_hash TYPE TEXT;


---------------------------------------------------------------------------
--Only for testing purpose


TRUNCATE TABLE user_otp, timesheet, users RESTART IDENTITY CASCADE;

-- 4 Dummy users
INSERT INTO users (username, email, password_hash, role, is_verified, is_active)
VALUES

-- Senior users
('Bob Senior', 'bob.senior@example.com', 'scrypt:32768:8:1$LMMQ19VwcAOGbIZB$a316ce0b1891ea21ba471fcc433bd060d36f290cee82161eec544b2fa690d0d491aa8505357fc86234640f00b4f228ed2da3aa2ff671dd4f75aece48790dfbd0', 'senior', TRUE, TRUE),
('Charlie Senior', 'charlie.senior@example.com', 'scrypt:32768:8:1$LMMQ19VwcAOGbIZB$a316ce0b1891ea21ba471fcc433bd060d36f290cee82161eec544b2fa690d0d491aa8505357fc86234640f00b4f228ed2da3aa2ff671dd4f75aece48790dfbd0', 'senior', TRUE, TRUE)

INSERT INTO users (username, email, password_hash, role, is_verified, is_active)
VALUES
-- Admin user
('Alice Admin', 'alice.admin@example.com', 'scrypt:32768:8:1$uwcTvIuvEcULYviY$755c07040fdb0950512fdfc51de15b4e8e9303dcd60da4cf2dde389fefdd2b0d26318855eebfad74f841068be9da0eb05549ed2bc8aee2b6498dc3bcfb3b3caf', 'admin', TRUE, TRUE)


-- Normal user
('David User', 'david.user@example.com', '$2b$12$dummyhashforuser', 'user', TRUE, TRUE);

---------------------------

select * from users
select * from user_otp
select * from timesheet
