# MAEH_DASHBOARD.py
"""
Midlands Academic Excellence Hub (MAEH)
Full Streamlit + Flask school dashboard with:

- Attendance (login/logout) via ESP32 callbacks
- Fingerprint enrollment workflow
- Enrollment status updates and progress
- Role-based views:
    - Admin
    - Teacher
    - Parent
    - Student
- Notifications system
- File uploads
- Student homework submissions
- Student marks and percentage calculation
- Subjects and teacher-subject assignments
- Parent/student performance monitoring
- Parent-student linking
- User management
- Safe SQLite database migrations

Notes:
- Set ESP32_BASE_URL to your ESP32 address.
- Files are stored under ./uploads.
- This script runs a Flask server on port 5000
  to receive ESP32 callbacks.
"""

# ============================================================
# IMPORTS
# ============================================================

import streamlit as st
import pandas as pd
import datetime
import sqlite3

from flask import Flask, request, make_response, jsonify

import threading
import os
import requests
import uuid
import time


# ============================================================
# CONFIGURATION
# ============================================================

ESP32_BASE_URL = "http://192.168.1.31"

DB_PATH = "attendance.db"

UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)


# ============================================================
# DATABASE CONNECTION
# ============================================================

conn = sqlite3.connect(
    DB_PATH,
    check_same_thread=False
)

cursor = conn.cursor()


# ============================================================
# DATABASE HELPERS
# ============================================================

def has_column(table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]


def ensure_schema():

    # --------------------------------------------------------
    # Attendance
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER,
            timestamp TEXT
        )
    """)

    # --------------------------------------------------------
    # Users
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            role TEXT,
            username TEXT UNIQUE,
            password TEXT
        )
    """)

    # --------------------------------------------------------
    # Marks
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS marks (
            id INTEGER,
            subject TEXT,
            mark REAL,
            timestamp TEXT
        )
    """)

    # --------------------------------------------------------
    # Students
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY,
            name TEXT
        )
    """)

    conn.commit()

    # --------------------------------------------------------
    # Attendance event migration
    # --------------------------------------------------------

    if not has_column("attendance", "event"):

        try:

            cursor.execute(
                "ALTER TABLE attendance ADD COLUMN event TEXT"
            )

            conn.commit()

            print("Added attendance.event")

        except Exception as e:

            print(
                "attendance.event migration error:",
                e
            )

    # --------------------------------------------------------
    # User student_id migration
    # --------------------------------------------------------

    if not has_column("users", "student_id"):

        try:

            cursor.execute(
                "ALTER TABLE users ADD COLUMN student_id INTEGER"
            )

            conn.commit()

            print("Added users.student_id")

        except Exception as e:

            print(
                "users.student_id migration error:",
                e
            )

    # --------------------------------------------------------
    # Student enrolled_at migration
    # --------------------------------------------------------

    if not has_column("students", "enrolled_at"):

        try:

            cursor.execute(
                "ALTER TABLE students ADD COLUMN enrolled_at TEXT"
            )

            conn.commit()

            print("Added students.enrolled_at")

        except Exception as e:

            print(
                "students.enrolled_at migration error:",
                e
            )

    # --------------------------------------------------------
    # Notifications
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_username TEXT,
            recipient_type TEXT,
            recipient_id INTEGER,
            title TEXT,
            message TEXT,
            attachment_path TEXT,
            timestamp TEXT
        )
    """)

    # --------------------------------------------------------
    # Homework submissions
    # --------------------------------------------------------

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            teacher_username TEXT,
            filename TEXT,
            filepath TEXT,
            message TEXT,
            timestamp TEXT
        )
    """)

    conn.commit()


ensure_schema()


# ============================================================
# SUBJECTS / MARKS DATABASE MIGRATION
# ============================================================

def ensure_subjects_schema():

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE,
            name TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teacher_subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_username TEXT,
            subject_id INTEGER
        )
    """)

    # --------------------------------------------------------
    # Check marks columns
    # --------------------------------------------------------

    cursor.execute("PRAGMA table_info(marks)")

    cols = [
        row[1]
        for row in cursor.fetchall()
    ]

    # Add subject if missing

    if "subject" not in cols:

        try:

            cursor.execute(
                "ALTER TABLE marks ADD COLUMN subject TEXT"
            )

            conn.commit()

            print("Added marks.subject")

        except Exception as e:

            print(
                "marks.subject migration error:",
                e
            )

    # Add percentage if missing

    if "percentage" not in cols:

        try:

            cursor.execute(
                "ALTER TABLE marks ADD COLUMN percentage REAL"
            )

            conn.commit()

            print("Added marks.percentage")

        except Exception as e:

            print(
                "marks.percentage migration error:",
                e
            )


ensure_subjects_schema()


# ============================================================
# DEFAULT SUBJECTS
# ============================================================

default_subjects = [
    ("MATH", "Mathematics"),
    ("ENG", "English"),
    ("SCI", "Science"),
    ("HIST", "History")
]

for code, name in default_subjects:

    try:

        cursor.execute(
            """
            INSERT OR IGNORE INTO subjects
            (code, name)
            VALUES (?, ?)
            """,
            (code, name)
        )

    except Exception:
        pass

conn.commit()


# ============================================================
# SIGNUP DATABASE MIGRATIONS
# ============================================================

def ensure_signup_fields():

    cursor.execute(
        "PRAGMA table_info(users)"
    )

    cols = [
        row[1]
        for row in cursor.fetchall()
    ]

    # Registration number

    if "reg_number" not in cols:

        try:

            cursor.execute(
                "ALTER TABLE users ADD COLUMN reg_number TEXT"
            )

            conn.commit()

        except Exception as e:

            print(
                "users.reg_number migration error:",
                e
            )

    # Date of birth

    if "dob" not in cols:

        try:

            cursor.execute(
                "ALTER TABLE users ADD COLUMN dob TEXT"
            )

            conn.commit()

        except Exception as e:

            print(
                "users.dob migration error:",
                e
            )

    # Email

    if "email" not in cols:

        try:

            cursor.execute(
                "ALTER TABLE users ADD COLUMN email TEXT"
            )

            conn.commit()

        except Exception as e:

            print(
                "users.email migration error:",
                e
            )


ensure_signup_fields()


# ============================================================
# DEFAULT ADMIN
# ============================================================

cursor.execute(
    "SELECT * FROM users WHERE username=?",
    ("Bishop",)
)

if not cursor.fetchone():

    cursor.execute(
        """
        INSERT INTO users
        (name, role, username, password)
        VALUES (?, ?, ?, ?)
        """,
        (
            "System Admin",
            "admin",
            "Bishop",
            "bishop2099"
        )
    )

    conn.commit()


# ============================================================
# FLASK SERVER
# ============================================================

app = Flask(__name__)


# ============================================================
# ESP32 ATTENDANCE ENDPOINT
# ============================================================

@app.route(
    "/attendance",
    methods=["POST"]
)
def attendance_endpoint():

    try:

        record = request.get_json(force=True)

        ts = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        cursor.execute(
            """
            INSERT INTO attendance
            (id, timestamp, event)
            VALUES (?, ?, ?)
            """,
            (
                record.get("id"),
                ts,
                record.get("event")
            )
        )

        conn.commit()

        return {
            "status": "success"
        }

    except Exception as e:

        print(
            "Attendance error:",
            e
        )

        return {
            "status": "error",
            "message": str(e)
        }, 500


# ============================================================
# ESP32 ENROLLMENT STATUS
# ============================================================

@app.route(
    "/enroll_status",
    methods=["POST"]
)
def enroll_status():

    try:

        record = request.get_json(force=True)

        status_message = record.get(
            "status",
            ""
        )

        print(
            "DEBUG: /enroll_status received:",
            status_message
        )

        timestamp = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        app.config[
            "last_enroll_status"
        ] = status_message

        app.config[
            "last_enroll_status_time"
        ] = timestamp

        return {
            "status": status_message
        }

    except Exception as e:

        print(
            "Enrollment status error:",
            e
        )

        return {
            "status": "error",
            "message": str(e)
        }, 500


# ============================================================
# ESP32 ENROLLMENT COMPLETE
# ============================================================

@app.route(
    "/enroll_complete",
    methods=["POST"]
)
def enroll_complete():

    try:

        record = request.get_json(force=True)

        enroll_id = record.get("id")

        enroll_name = record.get(
            "name",
            None
        )

        ts = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if enroll_id is None:

            return {
                "status": "error",
                "message": "missing id"
            }, 400

        cursor.execute(
            "SELECT name FROM students WHERE id=?",
            (enroll_id,)
        )

        existing = cursor.fetchone()

        if existing and existing[0] and not enroll_name:

            name_to_save = existing[0]

        else:

            name_to_save = (
                enroll_name
                or (existing[0] if existing else "")
            )

        cursor.execute(
            """
            INSERT OR REPLACE INTO students
            (id, name, enrolled_at)
            VALUES (?, ?, ?)
            """,
            (
                enroll_id,
                name_to_save,
                ts
            )
        )

        conn.commit()

        app.config[
            "last_enroll_complete"
        ] = {
            "id": enroll_id,
            "name": name_to_save,
            "time": ts
        }

        return {
            "status": "enrolled",
            "id": enroll_id
        }

    except Exception as e:

        print(
            "Enrollment complete error:",
            e
        )

        return {
            "status": "error",
            "message": str(e)
        }, 500


# ============================================================
# GET LATEST ENROLLMENT STATUS
# ============================================================

@app.route(
    "/get_latest_enroll_status",
    methods=["GET"]
)
def get_latest_enroll_status():

    status = app.config.get(
        "last_enroll_status",
        ""
    )

    status_time = app.config.get(
        "last_enroll_status_time",
        ""
    )

    response = make_response(
        jsonify(
            {
                "status": status,
                "time": status_time
            }
        )
    )

    response.headers[
        "Access-Control-Allow-Origin"
    ] = "*"

    return response


# ============================================================
# RUN FLASK
# ============================================================

def run_flask():

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False
    )


threading.Thread(
    target=run_flask,
    daemon=True
).start()


# ============================================================
# MAEH RED + WHITE THEME
# ============================================================

page_bg = """
<style>

:root {
    --maeh-red: #B5121B;
    --maeh-dark-red: #8F0D14;
    --maeh-light-red: #FDECEC;
    --maeh-white: #FFFFFF;
    --maeh-text: #2B2B2B;
    --maeh-border: #E8A0A4;
}


/* ========================================================
   MAIN APPLICATION BACKGROUND
   ======================================================== */

[data-testid="stAppViewContainer"] {

    background:
        linear-gradient(
            135deg,
            #FFFFFF 0%,
            #FFF7F7 45%,
            #FDECEC 100%
        );

    background-attachment: fixed;
}


/* ========================================================
   HEADER
   ======================================================== */

[data-testid="stHeader"] {

    background:
        rgba(255, 255, 255, 0.96);

}


/* ========================================================
   SIDEBAR
   ======================================================== */

[data-testid="stSidebar"] {

    background:
        linear-gradient(
            180deg,
            #B5121B 0%,
            #8F0D14 100%
        );

    padding-top: 10px;
}


/* Sidebar text */

[data-testid="stSidebar"] * {

    color: #FFFFFF !important;

}


/* Sidebar buttons */

[data-testid="stSidebar"] .stButton > button {

    background-color: #FFFFFF !important;

    color: #B5121B !important;

    border: 1px solid #FFFFFF !important;

    font-weight: 700;

}


/* Sidebar button hover */

[data-testid="stSidebar"] .stButton > button:hover {

    background-color: #FDECEC !important;

    color: #8F0D14 !important;

}


/* ========================================================
   MAIN CONTENT WIDTH
   ======================================================== */

.main .block-container {

    max-width: 1200px;

    padding-top: 1.5rem;

    padding-bottom: 3rem;

}


/* ========================================================
   HEADINGS
   ======================================================== */

h1,
h2,
h3 {

    color: #B5121B !important;

}


/* ========================================================
   DIVIDERS
   ======================================================== */

hr {

    border-color: #E8A0A4 !important;

}


/* ========================================================
   NORMAL BUTTONS
   ======================================================== */

.stButton > button {

    background-color: #B5121B;

    color: #FFFFFF;

    border: 1px solid #B5121B;

    border-radius: 8px;

    font-weight: 600;

    transition: all 0.2s ease;

}


.stButton > button:hover {

    background-color: #8F0D14;

    color: #FFFFFF;

    border-color: #8F0D14;

}


/* ========================================================
   FORM SUBMIT BUTTONS
   ======================================================== */

.stFormSubmitButton > button {

    background-color: #B5121B;

    color: #FFFFFF;

    border: 1px solid #B5121B;

    border-radius: 8px;

    font-weight: 600;

}


.stFormSubmitButton > button:hover {

    background-color: #8F0D14;

    color: #FFFFFF;

}


/* ========================================================
   TEXT INPUTS / SELECTS
   ======================================================== */

div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
textarea {

    border-color: #D9A0A3 !important;

}


div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="select"]:focus-within > div {

    border-color: #B5121B !important;

    box-shadow:
        0 0 0 1px #B5121B !important;

}


/* ========================================================
   PROGRESS BAR
   ======================================================== */

div[data-testid="stProgress"] > div > div {

    background-color: #B5121B;

}


/* ========================================================
   METRICS
   ======================================================== */

[data-testid="stMetric"] {

    background: #FFFFFF;

    border-left: 5px solid #B5121B;

    padding: 15px;

    border-radius: 8px;

    box-shadow:
        0 2px 8px rgba(181, 18, 27, 0.10);

}


/* ========================================================
   EXPANDERS
   ======================================================== */

[data-testid="stExpander"] {

    background-color: #FFFFFF;

    border: 1px solid #E8A0A4;

    border-radius: 8px;

}


/* ========================================================
   DATAFRAMES
   ======================================================== */

[data-testid="stDataFrame"] {

    border: 1px solid #E8A0A4;

    border-radius: 8px;

}


/* ========================================================
   ALERTS
   ======================================================== */

div[data-testid="stAlert"] {

    border-radius: 8px;

}


/* ========================================================
   MAEH CARD
   ======================================================== */

.maeh-card {

    background: #FFFFFF;

    padding: 30px;

    border-radius: 15px;

    border-top: 6px solid #B5121B;

    box-shadow:
        0 4px 18px rgba(181, 18, 27, 0.12);

}


/* ========================================================
   CENTERED LOGO
   ======================================================== */

.maeh-logo {

    display: flex;

    justify-content: center;

    align-items: center;

    width: 100%;

    margin-top: 10px;

    margin-bottom: 12px;

}


.maeh-logo img {

    width: 180px;

    max-width: 60%;

    height: auto;

    border-radius: 10px;

}


/* ========================================================
   SCHOOL TITLE
   ======================================================== */

.maeh-school-title {

    text-align: center;

    color: #B5121B;

    font-size: 32px;

    font-weight: 800;

    margin-top: 5px;

    margin-bottom: 5px;

}


/* ========================================================
   SCHOOL SUBTITLE
   ======================================================== */

.maeh-school-subtitle {

    text-align: center;

    color: #555555;

    font-size: 16px;

    margin-bottom: 25px;

}


/* ========================================================
   AUTH CARD
   ======================================================== */

.maeh-auth-card {

    background: #FFFFFF;

    border-radius: 15px;

    padding: 25px;

    box-shadow:
        0 4px 18px rgba(181, 18, 27, 0.10);

    border-top: 5px solid #B5121B;

}


/* ========================================================
   RED SECTION HEADER
   ======================================================== */

.maeh-section {

    background: #B5121B;

    color: #FFFFFF;

    padding: 12px 18px;

    border-radius: 8px;

    margin-top: 15px;

    margin-bottom: 15px;

    font-weight: 700;

}


</style>
"""

st.markdown(
    page_bg,
    unsafe_allow_html=True
)


# ============================================================
# CENTERED LOGO + SCHOOL TITLE
# ============================================================

logo_path = (
    os.path.join(
        os.path.dirname(__file__),
        "logo.jpg"
    )
    if "__file__" in globals()
    else "logo.jpg"
)


if os.path.exists(logo_path):

    with open(
        logo_path,
        "rb"
    ) as image_file:

        logo_bytes = image_file.read()

    import base64

    logo_base64 = base64.b64encode(
        logo_bytes
    ).decode()

    st.markdown(
        f"""
        <div class="maeh-logo">
            <img
                src="data:image/jpeg;base64,{logo_base64}"
                alt="MAEH Logo"
            >
        </div>

        <div class="maeh-school-title">
            Midlands Academic Excellence Hub
        </div>

        <div class="maeh-school-subtitle">
          Where knowledge meets excellence
        </div>
        """,
        unsafe_allow_html=True
    )

else:

    st.markdown(
        """
        <div class="maeh-school-title">
            Midlands Academic Excellence Hub
        </div>

        <div class="maeh-school-subtitle">
            School Management & Academic Dashboard
        </div>
        """,
        unsafe_allow_html=True
    )


# ============================================================
# SESSION STATE
# ============================================================

if "logged_in" not in st.session_state:

    st.session_state.logged_in = False

    st.session_state.user_role = None

    st.session_state.user_name = None


if "show_signup" not in st.session_state:

    st.session_state.show_signup = False


if "enroll_status" not in st.session_state:

    st.session_state.enroll_status = ""


if "enroll_progress" not in st.session_state:

    st.session_state.enroll_progress = 0


if "last_enroll_complete" not in st.session_state:

    st.session_state.last_enroll_complete = None


# ============================================================
# LOGIN FUNCTION
# ============================================================

def login(username, password):

    cursor.execute(
        """
        SELECT name, role
        FROM users
        WHERE username=?
        AND password=?
        """,
        (
            username,
            password
        )
    )

    return cursor.fetchone()


# ============================================================
# LOGIN / SIGNUP
# ============================================================

if not st.session_state.logged_in:

    st.header("Account Access")

    col1, col2 = st.columns(
        [2, 1]
    )

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    with col1:

        st.subheader("🔐 Login")

        login_username = st.text_input(
            "Username",
            key="login_username"
        )

        login_password = st.text_input(
            "Password",
            type="password",
            key="login_password"
        )

        if st.button(
            "Login",
            key="login_btn"
        ):

            user = login(
                login_username,
                login_password
            )

            if user:

                st.session_state.logged_in = True

                st.session_state.user_name = (
                    login_username
                )

                st.session_state.user_role = (
                    user[1]
                )

                st.success(
                    f"Welcome {user[0]} ({user[1]})"
                )

                st.rerun()

            else:

                st.error(
                    "Invalid credentials"
                )

        st.write("New here?")

        if st.button(
            "Create an account",
            key="open_signup_btn"
        ):

            st.session_state.show_signup = True

            st.rerun()

    # --------------------------------------------------------
    # SIGNUP
    # --------------------------------------------------------

    if st.session_state.show_signup:

        st.markdown("---")

        st.subheader("📝 Sign Up")

        with st.form("signup_form"):

            new_name = st.text_input(
                "Full Name",
                key="su_name"
            )

            new_role = st.selectbox(
                "Role",
                [
                    "teacher",
                    "parent",
                    "student"
                ],
                key="su_role"
            )

            new_reg = st.text_input(
                "Registration Number",
                key="su_reg"
            )

            new_dob = st.date_input(
                "Date of Birth",
                key="su_dob"
            )

            new_email = st.text_input(
                "Email",
                key="su_email"
            )

            new_username = st.text_input(
                "Choose a Username",
                key="su_username"
            )

            new_password = st.text_input(
                "Choose a Password",
                type="password",
                key="su_password"
            )

            submitted = st.form_submit_button(
                "Create Account",
                key="su_submit"
            )

            if submitted:

                if not (
                    new_name
                    and new_username
                    and new_password
                    and new_reg
                    and new_email
                ):

                    st.error(
                        "Please fill all required fields."
                    )

                else:

                    cursor.execute(
                        "SELECT id FROM users WHERE username=?",
                        (new_username,)
                    )

                    username_exists = cursor.fetchone()

                    cursor.execute(
                        "SELECT id FROM users WHERE email=?",
                        (new_email,)
                    )

                    email_exists = cursor.fetchone()

                    cursor.execute(
                        "SELECT id FROM users WHERE reg_number=?",
                        (new_reg,)
                    )

                    reg_exists = cursor.fetchone()

                    if username_exists:

                        st.error(
                            "That username is already taken."
                        )

                    elif email_exists:

                        st.error(
                            "That email is already registered."
                        )

                    elif reg_exists:

                        st.error(
                            "That registration number is already registered."
                        )

                    else:

                        try:

                            dob_str = (
                                new_dob.strftime("%Y-%m-%d")
                                if hasattr(
                                    new_dob,
                                    "strftime"
                                )
                                else str(new_dob)
                            )

                            cursor.execute(
                                """
                                INSERT INTO users
                                (
                                    name,
                                    role,
                                    username,
                                    password,
                                    reg_number,
                                    dob,
                                    email
                                )
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    new_name,
                                    new_role,
                                    new_username,
                                    new_password,
                                    new_reg,
                                    dob_str,
                                    new_email
                                )
                            )

                            conn.commit()

                            st.success(
                                f"Account created for "
                                f"{new_name} ({new_role})."
                            )

                            st.session_state.show_signup = False

                            st.rerun()

                        except sqlite3.IntegrityError:

                            st.error(
                                "Could not create account "
                                "because of a database constraint."
                            )

        if st.button(
            "Back to Login",
            key="back_to_login"
        ):

            st.session_state.show_signup = False

            st.rerun()

    st.stop()


# ============================================================
# SIDEBAR / LOGOUT
# ============================================================

st.sidebar.markdown(
    "---"
)

st.sidebar.write(
    f"👤 {st.session_state.user_name}"
)

st.sidebar.write(
    f"Role: {st.session_state.user_role}"
)

st.sidebar.markdown(
    "---"
)

if st.sidebar.button(
    "🚪 Logout"
):

    st.session_state.logged_in = False

    st.session_state.user_role = None

    st.session_state.user_name = None

    st.session_state.show_signup = False

    st.rerun()


role = st.session_state.user_role


# ============================================================
# ENROLLMENT PROGRESS
# ============================================================

PROGRESS_MAP = {

    "Place finger on sensor": 10,

    "Finger detected, processing...": 30,

    "Remove finger": 60,

    "Place same finger again": 80,

    "Enrollment successful!": 100,

    "Enrollment failed": 0,

    "Error capturing image": 0,

    "Error creating model": 0

}


def get_progress_for_status(status):

    if not status:

        return 0

    for key in PROGRESS_MAP:

        if key.lower() in status.lower():

            return PROGRESS_MAP[key]

    return 0


# ============================================================
# FILE UPLOAD HELPER
# ============================================================

def save_uploaded_file(
    uploaded_file,
    subfolder="general"
):

    ext = os.path.splitext(
        uploaded_file.name
    )[1]

    unique = str(uuid.uuid4())[:8]

    safe_name = (
        datetime.datetime.now().strftime(
            "%Y%m%d%H%M%S"
        )
        + "_"
        + unique
        + ext
    )

    folder = os.path.join(
        UPLOAD_DIR,
        subfolder
    )

    os.makedirs(
        folder,
        exist_ok=True
    )

    path = os.path.join(
        folder,
        safe_name
    )

    with open(
        path,
        "wb"
    ) as f:

        f.write(
            uploaded_file.getbuffer()
        )

    return (
        path,
        uploaded_file.name
    )


# ============================================================
# NOTIFICATION HELPER
# ============================================================

def create_notification(
    sender_username,
    recipient_type,
    recipient_id,
    title,
    message,
    attachment_path=None
):

    ts = datetime.datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    cursor.execute(
        """
        INSERT INTO notifications
        (
            sender_username,
            recipient_type,
            recipient_id,
            title,
            message,
            attachment_path,
            timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sender_username,
            recipient_type,
            recipient_id,
            title,
            message,
            attachment_path,
            ts
        )
    )

    conn.commit()


# ============================================================
# TEACHER VIEW
# ============================================================

if role == "teacher":

    st.header(
        "📘 Teacher Dashboard"
    )

    # --------------------------------------------------------
    # TEACHER SUBJECTS
    # --------------------------------------------------------

    def get_teacher_subjects(username):

        cursor.execute(
            """
            SELECT subject_id
            FROM teacher_subjects
            WHERE teacher_username=?
            """,
            (username,)
        )

        rows = cursor.fetchall()

        if rows:

            ids = [
                row[0]
                for row in rows
            ]

            if ids:

                placeholders = ",".join(
                    "?" * len(ids)
                )

                cursor.execute(
                    f"""
                    SELECT id, code, name
                    FROM subjects
                    WHERE id IN ({placeholders})
                    ORDER BY name
                    """,
                    ids
                )

                return cursor.fetchall()

        cursor.execute(
            """
            SELECT id, code, name
            FROM subjects
            ORDER BY name
            """
        )

        return cursor.fetchall()


    # --------------------------------------------------------
    # ENTER MARKS
    # --------------------------------------------------------

    st.subheader(
        "Enter Student Marks"
    )

    teacher_subject_rows = get_teacher_subjects(
        st.session_state.user_name
    )

    subject_options = [
        f"{row[1]} - {row[2]}"
        for row in teacher_subject_rows
    ]

    subject_map = {
        f"{row[1]} - {row[2]}": row[2]
        for row in teacher_subject_rows
    }

    with st.form("add_marks"):

        student_id = st.number_input(
            "Student Fingerprint ID",
            min_value=1,
            step=1
        )

        if subject_options:

            subject_choice = st.selectbox(
                "Subject",
                subject_options
            )

            subject_name = subject_map[
                subject_choice
            ]

        else:

            subject_name = st.text_input(
                "Subject name"
            )

        raw_mark = st.number_input(
            "Mark obtained",
            min_value=0.0,
            step=0.1
        )

        max_mark = st.number_input(
            "Max mark",
            min_value=1.0,
            value=100.0,
            step=1.0
        )

        submitted = st.form_submit_button(
            "Save Mark"
        )

        if submitted:

            if not subject_name:

                st.error(
                    "Please select or enter a subject."
                )

            else:

                percentage = round(
                    (raw_mark / max_mark) * 100.0,
                    2
                )

                ts = datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                cursor.execute(
                    """
                    INSERT INTO marks
                    (
                        id,
                        subject,
                        mark,
                        percentage,
                        timestamp
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        student_id,
                        subject_name,
                        raw_mark,
                        percentage,
                        ts
                    )
                )

                conn.commit()

                st.success(
                    f"Saved: Student {student_id} — "
                    f"{subject_name} — "
                    f"{raw_mark}/{max_mark} → "
                    f"{percentage}%"
                )


    st.markdown("---")


    # --------------------------------------------------------
    # TEACHER NOTIFICATIONS
    # --------------------------------------------------------

    st.subheader(
        "📢 Send Notification"
    )

    with st.form("teacher_notify"):

        notify_target = st.selectbox(
            "Recipient type",
            [
                "all",
                "parents",
                "students",
                "specific_student"
            ]
        )

        specific_student_id = None

        if notify_target == "specific_student":

            specific_student_id = st.number_input(
                "Student ID",
                min_value=1,
                step=1
            )

        title = st.text_input(
            "Title"
        )

        message = st.text_area(
            "Message"
        )

        attach = st.file_uploader(
            "Attach file (optional)",
            type=None
        )

        send = st.form_submit_button(
            "Send Notification"
        )

        if send:

            attachment_path = None

            if attach:

                attachment_path, original_name = (
                    save_uploaded_file(
                        attach,
                        subfolder="notifications"
                    )
                )

            if notify_target == "all":

                recipient_type = "all"

            elif notify_target == "parents":

                recipient_type = "parent"

            elif notify_target == "students":

                recipient_type = "student"

            else:

                recipient_type = "student"

            recipient_id = (
                specific_student_id
                if notify_target == "specific_student"
                else None
            )

            create_notification(
                st.session_state.user_name,
                recipient_type,
                recipient_id,
                title,
                message,
                attachment_path
            )

            st.success(
                "Notification created and saved."
            )


    st.markdown("---")


    # --------------------------------------------------------
    # ATTENDANCE
    # --------------------------------------------------------

    st.subheader(
        "📋 Attendance Logs"
    )

    df = pd.read_sql_query(
        """
        SELECT
            a.id,
            s.name,
            a.timestamp,
            a.event
        FROM attendance a
        LEFT JOIN students s
            ON a.id = s.id
        ORDER BY a.timestamp DESC
        """,
        conn
    )

    st.dataframe(
        df,
        use_container_width=True
    )


    st.markdown("---")


    # --------------------------------------------------------
    # STUDENT SUBMISSIONS
    # --------------------------------------------------------

    st.subheader(
        "📚 Student Submissions"
    )

    subs = pd.read_sql_query(
        """
        SELECT *
        FROM submissions
        ORDER BY timestamp DESC
        """,
        conn
    )

    if subs.empty:

        st.info(
            "No submissions yet."
        )

    else:

        for _, row in subs.iterrows():

            st.write(
                f"**Student ID:** "
                f"{row['student_id']}"
            )

            st.write(
                f"**Message:** "
                f"{row['message']}"
            )

            st.write(
                f"**Time:** "
                f"{row['timestamp']}"
            )

            if (
                row["filepath"]
                and os.path.exists(
                    row["filepath"]
                )
            ):

                with open(
                    row["filepath"],
                    "rb"
                ) as f:

                    data = f.read()

                st.download_button(
                    label=(
                        f"Download "
                        f"{row['filename']}"
                    ),
                    data=data,
                    file_name=row["filename"],
                    key=f"download_submission_{row['id']}"
                )

            st.markdown("---")


    # --------------------------------------------------------
    # NOTIFICATIONS SENT
    # --------------------------------------------------------

    st.subheader(
        "📨 Notifications Sent"
    )

    nots = pd.read_sql_query(
        """
        SELECT *
        FROM notifications
        WHERE sender_username=?
        ORDER BY timestamp DESC
        """,
        conn,
        params=(
            st.session_state.user_name,
        )
    )

    if nots.empty:

        st.info(
            "No notifications sent yet."
        )

    else:

        st.dataframe(
            nots,
            use_container_width=True
        )


# ============================================================
# PARENT VIEW
# ============================================================

elif role == "parent":

    st.header(
        "👨‍👩‍👧 Parent Dashboard"
    )

    # --------------------------------------------------------
    # LINKED STUDENT
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT
            s.name,
            u.student_id
        FROM users u
        LEFT JOIN students s
            ON u.student_id = s.id
        WHERE u.username=?
        """,
        (
            st.session_state.user_name,
        )
    )

    linked = cursor.fetchone()

    if linked and linked[0]:

        st.success(
            f"Linked student: "
            f"{linked[0]} "
            f"(ID {linked[1]})"
        )

    else:

        st.warning(
            "No student linked to this parent account. "
            "Contact the administrator."
        )


    st.markdown("---")


    # --------------------------------------------------------
    # ATTENDANCE
    # --------------------------------------------------------

    if linked and linked[1]:

        student_id = linked[1]

        st.subheader(
            "📋 Student Attendance"
        )

        df = pd.read_sql_query(
            """
            SELECT
                a.id,
                s.name,
                a.timestamp,
                a.event
            FROM attendance a
            LEFT JOIN students s
                ON a.id = s.id
            WHERE a.id=?
            ORDER BY a.timestamp DESC
            """,
            conn,
            params=(student_id,)
        )

        if df.empty:

            st.info(
                "No attendance records yet."
            )

        else:

            st.dataframe(
                df,
                use_container_width=True
            )


    st.markdown("---")


    # --------------------------------------------------------
    # PARENT NOTIFICATIONS
    # --------------------------------------------------------

    st.subheader(
        "📢 Notifications"
    )

    if linked and linked[1]:

        student_id = linked[1]

        nots = pd.read_sql_query(
            """
            SELECT *
            FROM notifications
            WHERE
                recipient_type='all'
                OR recipient_type='parent'
                OR (
                    recipient_type='student'
                    AND recipient_id=?
                )
            ORDER BY timestamp DESC
            """,
            conn,
            params=(student_id,)
        )

    else:

        nots = pd.read_sql_query(
            """
            SELECT *
            FROM notifications
            WHERE
                recipient_type='all'
                OR recipient_type='parent'
            ORDER BY timestamp DESC
            """,
            conn
        )


    if nots.empty:

        st.info(
            "No notifications yet."
        )

    else:

        for _, row in nots.iterrows():

            st.write(
                f"**From:** "
                f"{row['sender_username']}"
            )

            st.caption(
                row["timestamp"]
            )

            st.write(
                f"### {row['title']}"
            )

            st.write(
                row["message"]
            )

            if (
                row["attachment_path"]
                and os.path.exists(
                    row["attachment_path"]
                )
            ):

                with open(
                    row["attachment_path"],
                    "rb"
                ) as f:

                    data = f.read()

                st.download_button(
                    label="Download attachment",
                    data=data,
                    file_name=os.path.basename(
                        row["attachment_path"]
                    ),
                    key=f"parent_download_{row['id']}"
                )

            st.markdown("---")


    # --------------------------------------------------------
    # PERFORMANCE
    # --------------------------------------------------------

    st.subheader(
        "📊 Student Performance by Subject"
    )

    if linked and linked[1]:

        student_id = linked[1]

        subj_rows = pd.read_sql_query(
            """
            SELECT DISTINCT subject
            FROM marks
            WHERE id=?
            ORDER BY subject
            """,
            conn,
            params=(student_id,)
        )

        all_subjects = (
            subj_rows["subject"].tolist()
            if not subj_rows.empty
            else []
        )

        if not all_subjects:

            srows = pd.read_sql_query(
                """
                SELECT name
                FROM subjects
                ORDER BY name
                """,
                conn
            )

            all_subjects = (
                srows["name"].tolist()
                if not srows.empty
                else []
            )


        if all_subjects:

            chosen = st.selectbox(
                "Select subject",
                all_subjects
            )

            df_marks = pd.read_sql_query(
                """
                SELECT
                    mark,
                    percentage,
                    timestamp
                FROM marks
                WHERE id=?
                AND subject=?
                ORDER BY timestamp DESC
                """,
                conn,
                params=(
                    student_id,
                    chosen
                )
            )

            if df_marks.empty:

                st.info(
                    "No marks recorded yet "
                    "for this subject."
                )

            else:

                st.write(
                    f"Performance for {chosen}"
                )

                st.dataframe(
                    df_marks,
                    use_container_width=True
                )

                df_chart = df_marks.copy()

                df_chart["timestamp"] = (
                    pd.to_datetime(
                        df_chart["timestamp"]
                    )
                )

                df_chart = df_chart.sort_values(
                    "timestamp"
                )

                st.line_chart(
                    df_chart.set_index(
                        "timestamp"
                    )["percentage"]
                )

                avg_pct = round(
                    df_chart["percentage"].mean(),
                    2
                )

                st.metric(
                    "Average percentage",
                    f"{avg_pct}%"
                )

        else:

            st.info(
                "No subjects available yet."
            )

    else:

        st.info(
            "No student linked to this parent account."
        )


# ============================================================
# STUDENT VIEW
# ============================================================

elif role == "student":

    st.header(
        "🎒 Student Dashboard"
    )

    # --------------------------------------------------------
    # FIND STUDENT ID
    # --------------------------------------------------------

    cursor.execute(
        """
        SELECT student_id
        FROM users
        WHERE username=?
        """,
        (
            st.session_state.user_name,
        )
    )

    res = cursor.fetchone()

    student_id = (
        res[0]
        if res
        else None
    )


    # --------------------------------------------------------
    # ATTENDANCE
    # --------------------------------------------------------

    if student_id:

        st.subheader(
            "📋 Attendance Logs"
        )

        df = pd.read_sql_query(
            """
            SELECT
                a.id,
                s.name,
                a.timestamp,
                a.event
            FROM attendance a
            LEFT JOIN students s
                ON a.id = s.id
            WHERE a.id=?
            ORDER BY a.timestamp DESC
            """,
            conn,
            params=(student_id,)
        )

        if df.empty:

            st.info(
                "No attendance records yet."
            )

        else:

            st.dataframe(
                df,
                use_container_width=True
            )

    else:

        st.info(
            "No student ID linked to your account. "
            "Contact the administrator."
        )


    st.markdown("---")


    # --------------------------------------------------------
    # HOMEWORK
    # --------------------------------------------------------

    st.subheader(
        "📚 Upload Homework / Submission"
    )

    teachers = pd.read_sql_query(
        """
        SELECT username, name
        FROM users
        WHERE role='teacher'
        ORDER BY name
        """,
        conn
    )

    teacher_usernames = (
        teachers["username"].tolist()
        if not teachers.empty
        else []
    )


    with st.form("upload_homework"):

        if teacher_usernames:

            teacher_choice = st.selectbox(
                "Select Teacher",
                teacher_usernames
            )

        else:

            teacher_choice = st.text_input(
                "Teacher Username"
            )

        hw_file = st.file_uploader(
            "Choose homework file",
            type=None
        )

        hw_message = st.text_area(
            "Message (optional)"
        )

        submit_hw = st.form_submit_button(
            "Upload Homework"
        )

        if submit_hw:

            if not student_id:

                st.error(
                    "Your account is not linked "
                    "to a student record."
                )

            elif not teacher_choice:

                st.error(
                    "Please select a teacher."
                )

            elif not hw_file:

                st.error(
                    "Please choose a file."
                )

            else:

                path, orig_name = (
                    save_uploaded_file(
                        hw_file,
                        subfolder="submissions"
                    )
                )

                ts = datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                cursor.execute(
                    """
                    INSERT INTO submissions
                    (
                        student_id,
                        teacher_username,
                        filename,
                        filepath,
                        message,
                        timestamp
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        student_id,
                        teacher_choice,
                        orig_name,
                        path,
                        hw_message,
                        ts
                    )
                )

                conn.commit()

                # Store teacher-specific notification
                cursor.execute(
                    """
                    SELECT id
                    FROM users
                    WHERE username=?
                    AND role='teacher'
                    """,
                    (teacher_choice,)
                )

                teacher_row = cursor.fetchone()

                teacher_id = (
                    teacher_row[0]
                    if teacher_row
                    else None
                )

                create_notification(
                    st.session_state.user_name,
                    "teacher",
                    teacher_id,
                    f"Homework from student {student_id}",
                    hw_message or "(no message)",
                    path
                )

                st.success(
                    "Homework uploaded "
                    "and teacher notified."
                )


    st.markdown("---")


    # --------------------------------------------------------
    # STUDENT NOTIFICATIONS
    # --------------------------------------------------------

    st.subheader(
        "📢 Notifications"
    )

    if student_id:

        nots = pd.read_sql_query(
            """
            SELECT *
            FROM notifications
            WHERE
                recipient_type='all'
                OR (
                    recipient_type='student'
                    AND (
                        recipient_id IS NULL
                        OR recipient_id=?
                    )
                )
            ORDER BY timestamp DESC
            """,
            conn,
            params=(student_id,)
        )

    else:

        nots = pd.read_sql_query(
            """
            SELECT *
            FROM notifications
            WHERE recipient_type='all'
            ORDER BY timestamp DESC
            """,
            conn
        )


    if nots.empty:

        st.info(
            "No notifications yet."
        )

    else:

        for _, row in nots.iterrows():

            st.write(
                f"**From:** "
                f"{row['sender_username']}"
            )

            st.caption(
                row["timestamp"]
            )

            st.write(
                f"### {row['title']}"
            )

            st.write(
                row["message"]
            )

            if (
                row["attachment_path"]
                and os.path.exists(
                    row["attachment_path"]
                )
            ):

                with open(
                    row["attachment_path"],
                    "rb"
                ) as f:

                    data = f.read()

                st.download_button(
                    label="Download attachment",
                    data=data,
                    file_name=os.path.basename(
                        row["attachment_path"]
                    ),
                    key=f"student_download_{row['id']}"
                )

            st.markdown("---")


# ============================================================
# ADMIN VIEW
# ============================================================

elif role == "admin":

    st.header(
        "⚙️ Admin Dashboard"
    )


    # ========================================================
    # REGISTER STUDENT MANUALLY
    # ========================================================

    st.subheader(
        "Register Students"
    )

    with st.form("add_student"):

        student_id = st.number_input(
            "Student Fingerprint ID",
            min_value=1,
            step=1,
            key="reg_id"
        )

        student_name = st.text_input(
            "Student Name",
            key="reg_name"
        )

        submitted = st.form_submit_button(
            "Add Student"
        )

        if submitted:

            if not student_name:

                st.error(
                    "Enter student name."
                )

            else:

                ts = datetime.datetime.now().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                cursor.execute(
                    """
                    INSERT OR REPLACE INTO students
                    (
                        id,
                        name,
                        enrolled_at
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        student_id,
                        student_name,
                        ts
                    )
                )

                conn.commit()

                st.success(
                    f"Student {student_name} "
                    f"(ID {student_id}) saved!"
                )


    st.markdown("---")


    # ========================================================
    # ESP32 FINGERPRINT ENROLLMENT
    # ========================================================

    st.subheader(
        "🖐️ Enroll New Student via Fingerprint Sensor"
    )

    with st.form("enroll_form"):

        enroll_id = st.number_input(
            "Assign Fingerprint ID",
            min_value=1,
            step=1,
            key="enroll_id"
        )

        enroll_name = st.text_input(
            "Student Name (optional)",
            key="enroll_name"
        )

        start_enroll = st.form_submit_button(
            "Start Enrollment on ESP32"
        )

        if start_enroll:

            if (
                not ESP32_BASE_URL
                or "YOUR_ESP32_IP" in ESP32_BASE_URL
            ):

                st.error(
                    "Set ESP32_BASE_URL at the top "
                    "of this file."
                )

            else:

                try:

                    response = requests.post(
                        f"{ESP32_BASE_URL}/start_enroll",
                        json={
                            "id": int(enroll_id),
                            "name": enroll_name
                        },
                        timeout=5
                    )

                    if response.status_code == 200:

                        st.success(
                            "Enrollment started on ESP32."
                        )

                        st.session_state.enroll_status = ""

                        st.session_state.enroll_progress = 0

                        st.session_state[
                            "_pending_enroll"
                        ] = {
                            "id": int(enroll_id),
                            "name": enroll_name
                        }

                    else:

                        st.error(
                            f"ESP32 responded with "
                            f"status "
                            f"{response.status_code}: "
                            f"{response.text}"
                        )

                except Exception as e:

                    st.error(
                        f"Could not reach ESP32: {e}"
                    )


    # ========================================================
    # ENROLLMENT STATUS
    # ========================================================

    st.markdown("---")

    st.subheader(
        "📡 Enrollment Status"
    )


    if st.button(
        "Refresh enrollment status"
    ):

        st.session_state.enroll_status = (
            app.config.get(
                "last_enroll_status",
                ""
            )
        )

        st.session_state.enroll_status_time = (
            app.config.get(
                "last_enroll_status_time",
                ""
            )
        )

        st.rerun()


    # --------------------------------------------------------
    # Live settings
    # --------------------------------------------------------

    if "enroll_live" not in st.session_state:

        st.session_state.enroll_live = False


    if "enroll_poll_seconds" not in st.session_state:

        st.session_state.enroll_poll_seconds = 30


    if "enroll_interval" not in st.session_state:

        st.session_state.enroll_interval = 1


    cols = st.columns(
        [2, 1, 1]
    )


    with cols[0]:

        st.session_state.enroll_poll_seconds = (
            st.number_input(
                "Live poll duration (seconds)",
                min_value=5,
                max_value=300,
                value=st.session_state.enroll_poll_seconds,
                step=5
            )
        )


    with cols[1]:

        st.session_state.enroll_interval = (
            st.number_input(
                "Poll interval (seconds)",
                min_value=1,
                max_value=10,
                value=st.session_state.enroll_interval,
                step=1
            )
        )


    with cols[2]:

        if st.session_state.enroll_live:

            if st.button(
                "Stop live updates"
            ):

                st.session_state.enroll_live = False

                st.rerun()

        else:

            if st.button(
                "Start live updates"
            ):

                st.session_state.enroll_live = True

                st.rerun()


    status_placeholder = st.empty()


    # --------------------------------------------------------
    # Fetch status
    # --------------------------------------------------------

    def fetch_latest_status():

        try:

            response = requests.get(
                "http://127.0.0.1:5000/"
                "get_latest_enroll_status",
                timeout=2
            )

            if response.status_code == 200:

                data = response.json()

                return (
                    data.get("status", ""),
                    data.get("time", "")
                )

        except Exception:

            return (
                app.config.get(
                    "last_enroll_status",
                    ""
                ),
                app.config.get(
                    "last_enroll_status_time",
                    ""
                )
            )

        return "", ""


    # --------------------------------------------------------
    # Display current status
    # --------------------------------------------------------

    status = (
        st.session_state.get(
            "enroll_status"
        )
        or app.config.get(
            "last_enroll_status",
            ""
        )
    )

    status_time = (
        st.session_state.get(
            "enroll_status_time"
        )
        or app.config.get(
            "last_enroll_status_time",
            ""
        )
    )


    if status:

        status_placeholder.info(
            f"📢 Status: {status} "
            f"— {status_time}"
        )

        st.progress(
            get_progress_for_status(
                status
            )
        )

    else:

        status_placeholder.write(
            "No enrollment activity yet."
        )


    # --------------------------------------------------------
    # Poll ESP32
    # --------------------------------------------------------

    if st.session_state.enroll_live:

        start = time.time()

        timeout = float(
            st.session_state.enroll_poll_seconds
        )

        interval = float(
            st.session_state.enroll_interval
        )

        while (
            time.time() - start < timeout
            and st.session_state.enroll_live
        ):

            current_status, current_time = (
                fetch_latest_status()
            )

            if current_status:

                st.session_state.enroll_status = (
                    current_status
                )

                st.session_state.enroll_status_time = (
                    current_time
                )

                status_placeholder.info(
                    f"📢 Status: "
                    f"{current_status} "
                    f"— {current_time}"
                )

                st.progress(
                    get_progress_for_status(
                        current_status
                    )
                )

                if any(
                    key in current_status.lower()
                    for key in [
                        "enrollment successful",
                        "enrolled",
                        "enrollment failed"
                    ]
                ):

                    st.session_state.enroll_live = False

                    break

            else:

                status_placeholder.write(
                    "Waiting for enrollment status..."
                )

            time.sleep(
                interval
            )

        st.session_state.enroll_live = False


    # ========================================================
    # LAST COMPLETED ENROLLMENT
    # ========================================================

    last_complete = (
        st.session_state.get(
            "last_enroll_complete"
        )
        or app.config.get(
            "last_enroll_complete"
        )
    )


    if last_complete:

        st.success(
            f"Enrollment complete: "
            f"ID {last_complete['id']} "
            f"Name: "
            f"{last_complete.get('name') or '(none)'} "
            f"at {last_complete['time']}"
        )

        cursor.execute(
            """
            SELECT id
            FROM students
            WHERE id=?
            """,
            (
                last_complete["id"],
            )
        )

        if not cursor.fetchone():

            pending = st.session_state.get(
                "_pending_enroll",
                {}
            )

            name_to_save = (
                last_complete.get("name")
                or pending.get("name")
                or ""
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO students
                (
                    id,
                    name,
                    enrolled_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    last_complete["id"],
                    name_to_save,
                    last_complete["time"]
                )
            )

            conn.commit()

            st.info(
                "Student record saved to database."
            )

        if "_pending_enroll" in st.session_state:

            del st.session_state[
                "_pending_enroll"
            ]


    st.markdown("---")


    # ========================================================
    # ADMIN NOTIFICATIONS
    # ========================================================

    st.subheader(
        "📢 Send Notification"
    )

    with st.form("admin_notify"):

        recipient_type = st.selectbox(
            "Recipient type",
            [
                "all",
                "parents",
                "students",
                "teachers",
                "specific_student",
                "specific_teacher"
            ]
        )

        recipient_id = None

        recipient_username = None


        if recipient_type == "specific_student":

            recipient_id = st.number_input(
                "Student ID",
                min_value=1,
                step=1
            )


        if recipient_type == "specific_teacher":

            recipient_username = st.text_input(
                "Teacher username"
            )


        title = st.text_input(
            "Title"
        )

        message = st.text_area(
            "Message"
        )

        attach = st.file_uploader(
            "Attach file (optional)",
            type=None
        )

        send = st.form_submit_button(
            "Send"
        )


        if send:

            attachment_path = None

            if attach:

                attachment_path, original_name = (
                    save_uploaded_file(
                        attach,
                        subfolder="notifications"
                    )
                )


            # ------------------------------------------------
            # Correct recipient mapping
            # ------------------------------------------------

            if recipient_type == "all":

                stored_type = "all"

                stored_id = None


            elif recipient_type == "parents":

                stored_type = "parent"

                stored_id = None


            elif recipient_type == "students":

                stored_type = "student"

                stored_id = None


            elif recipient_type == "teachers":

                stored_type = "teacher"

                stored_id = None


            elif recipient_type == "specific_student":

                stored_type = "student"

                stored_id = recipient_id


            elif recipient_type == "specific_teacher":

                stored_type = "teacher"

                stored_id = None

                if recipient_username:

                    cursor.execute(
                        """
                        SELECT id
                        FROM users
                        WHERE username=?
                        AND role='teacher'
                        """,
                        (
                            recipient_username,
                        )
                    )

                    teacher_row = cursor.fetchone()

                    if teacher_row:

                        stored_id = teacher_row[0]

                    else:

                        st.error(
                            "Teacher username not found."
                        )

                        st.stop()


            create_notification(
                st.session_state.user_name,
                stored_type,
                stored_id,
                title,
                message,
                attachment_path
            )

            st.success(
                "Notification created."
            )


    st.markdown("---")


    # ========================================================
    # LINK PARENT TO STUDENT
    # ========================================================

    st.subheader(
        "🔗 Link Parent to Student"
    )

    students_list = pd.read_sql_query(
        """
        SELECT id, name
        FROM students
        ORDER BY name
        """,
        conn
    )


    if students_list.empty:

        st.info(
            "No students have been registered yet."
        )

    else:

        with st.form("link_parent"):

            parent_username = st.text_input(
                "Parent Username"
            )

            student_choice = st.selectbox(
                "Select Student",
                [
                    f"{row['name']} "
                    f"(ID {row['id']})"
                    for _, row
                    in students_list.iterrows()
                ]
            )

            submitted = st.form_submit_button(
                "Link"
            )

            if submitted:

                if not parent_username:

                    st.error(
                        "Enter parent username."
                    )

                else:

                    student_id = int(
                        student_choice
                        .split("(ID ")[1]
                        .replace(")", "")
                    )

                    cursor.execute(
                        """
                        SELECT id
                        FROM users
                        WHERE username=?
                        AND role='parent'
                        """,
                        (
                            parent_username,
                        )
                    )

                    parent_exists = cursor.fetchone()

                    if not parent_exists:

                        st.error(
                            "Parent username not found."
                        )

                    else:

                        cursor.execute(
                            """
                            UPDATE users
                            SET student_id=?
                            WHERE username=?
                            AND role='parent'
                            """,
                            (
                                student_id,
                                parent_username
                            )
                        )

                        conn.commit()

                        st.success(
                            "Parent linked to student."
                        )


    st.markdown("---")


    # ========================================================
    # SUBJECT MANAGEMENT
    # ========================================================

    st.subheader(
        "📚 Manage Subjects"
    )

    with st.form("add_subject"):

        subj_code = st.text_input(
            "Subject code (e.g. MATH)"
        )

        subj_name = st.text_input(
            "Subject name (e.g. Mathematics)"
        )

        add_sub = st.form_submit_button(
            "Add Subject"
        )

        if add_sub:

            if subj_code and subj_name:

                cursor.execute(
                    """
                    INSERT OR IGNORE INTO subjects
                    (code, name)
                    VALUES (?, ?)
                    """,
                    (
                        subj_code.upper(),
                        subj_name
                    )
                )

                conn.commit()

                st.success(
                    "Subject added."
                )

            else:

                st.error(
                    "Provide both code and name."
                )


    # ========================================================
    # TEACHER SUBJECT ASSIGNMENTS
    # ========================================================

    st.subheader(
        "👨‍🏫 Teacher Subject Assignments"
    )

    teachers = pd.read_sql_query(
        """
        SELECT username, name
        FROM users
        WHERE role='teacher'
        ORDER BY name
        """,
        conn
    )

    teacher_usernames = (
        teachers["username"].tolist()
        if not teachers.empty
        else []
    )


    subjects_df = pd.read_sql_query(
        """
        SELECT id, code, name
        FROM subjects
        ORDER BY name
        """,
        conn
    )


    subject_display = [
        f"{row['id']}|"
        f"{row['code']} - "
        f"{row['name']}"
        for _, row
        in subjects_df.iterrows()
    ]


    with st.form("assign_subject"):

        if teacher_usernames:

            t_user = st.selectbox(
                "Teacher",
                teacher_usernames
            )

        else:

            t_user = st.text_input(
                "Teacher username"
            )


        if subject_display:

            subj_choice = st.selectbox(
                "Subject",
                subject_display
            )

        else:

            subj_choice = st.text_input(
                "Subject id|code - name"
            )


        assign = st.form_submit_button(
            "Assign"
        )


        if assign:

            if t_user and subj_choice:

                try:

                    subj_id = int(
                        subj_choice.split("|")[0]
                    )

                    # Avoid duplicate assignments

                    cursor.execute(
                        """
                        SELECT id
                        FROM teacher_subjects
                        WHERE teacher_username=?
                        AND subject_id=?
                        """,
                        (
                            t_user,
                            subj_id
                        )
                    )

                    existing_assignment = (
                        cursor.fetchone()
                    )

                    if existing_assignment:

                        st.warning(
                            "This subject is already "
                            "assigned to this teacher."
                        )

                    else:

                        cursor.execute(
                            """
                            INSERT INTO teacher_subjects
                            (
                                teacher_username,
                                subject_id
                            )
                            VALUES (?, ?)
                            """,
                            (
                                t_user,
                                subj_id
                            )
                        )

                        conn.commit()

                        st.success(
                            "Subject assigned to teacher."
                        )

                except Exception as e:

                    st.error(
                        f"Could not assign subject: {e}"
                    )

            else:

                st.error(
                    "Select teacher and subject."
                )


    st.markdown("---")


    # ========================================================
    # ENROLLED STUDENTS
    # ========================================================

    st.subheader(
        "👨‍🎓 Students Enrolled"
    )

    df_students = pd.read_sql_query(
        """
        SELECT
            id,
            name,
            enrolled_at
        FROM students
        ORDER BY name
        """,
        conn
    )

    st.dataframe(
        df_students,
        use_container_width=True
    )


    st.markdown("---")


    # ========================================================
    # MARKS OVERVIEW
    # ========================================================

    st.subheader(
        "📊 Marks Overview"
    )

    df_marks_overview = pd.read_sql_query(
        """
        SELECT
            m.id,
            s.name AS student_name,
            m.subject,
            m.mark,
            m.percentage,
            m.timestamp
        FROM marks m
        LEFT JOIN students s
            ON m.id = s.id
        ORDER BY m.timestamp DESC
        """,
        conn
    )

    st.dataframe(
        df_marks_overview,
        use_container_width=True
    )


    st.markdown("---")


    # ========================================================
    # MANAGE USERS
    # ========================================================

    st.subheader(
        "👥 Manage Users"
    )

    st.write(
        "View registered users and remove accounts "
        "when necessary."
    )


    users_df = pd.read_sql_query(
        """
        SELECT
            id,
            name,
            role,
            username,
            reg_number,
            dob,
            email,
            student_id
        FROM users
        ORDER BY role, name
        """,
        conn
    )


    if users_df.empty:

        st.info(
            "No users found."
        )

    else:

        filter_cols = st.columns(
            [3, 2, 2]
        )


        with filter_cols[0]:

            search_name = st.text_input(
                "Search name or username",
                value=""
            )


        with filter_cols[1]:

            filter_role = st.selectbox(
                "Filter by role",
                [
                    "all",
                    "admin",
                    "teacher",
                    "parent",
                    "student"
                ]
            )


        with filter_cols[2]:

            if st.button(
                "Refresh list"
            ):

                st.rerun()


        qdf = users_df.copy()


        if search_name:

            qdf = qdf[
                qdf["name"].fillna("").str.contains(
                    search_name,
                    case=False,
                    na=False
                )
                |
                qdf["username"].fillna("").str.contains(
                    search_name,
                    case=False,
                    na=False
                )
            ]


        if (
            filter_role
            and filter_role != "all"
        ):

            qdf = qdf[
                qdf["role"] == filter_role
            ]


        # ----------------------------------------------------
        # User cards
        # ----------------------------------------------------

        for _, row in qdf.iterrows():

            uid = int(row["id"])

            uname = row["username"]

            urole = row["role"]

            display_name = (
                f"{row['name']} "
                f"({uname}) — {urole}"
            )


            with st.expander(
                display_name,
                expanded=False
            ):

                st.write(
                    f"**Name:** {row['name']}"
                )

                st.write(
                    f"**Username:** {uname}"
                )

                st.write(
                    f"**Role:** {urole}"
                )


                if not pd.isna(
                    row.get("reg_number")
                ):

                    st.write(
                        f"**Registration Number:** "
                        f"{row['reg_number']}"
                    )


                if not pd.isna(
                    row.get("email")
                ):

                    st.write(
                        f"**Email:** "
                        f"{row['email']}"
                    )


                if not pd.isna(
                    row.get("dob")
                ):

                    st.write(
                        f"**Date of Birth:** "
                        f"{row['dob']}"
                    )


                if not pd.isna(
                    row.get("student_id")
                ):

                    st.write(
                        f"**Linked Student ID:** "
                        f"{int(row['student_id'])}"
                    )


                # ------------------------------------------------
                # Delete confirmation
                # ------------------------------------------------

                delete_key = (
                    f"del_confirm_{uid}"
                )


                if delete_key not in st.session_state:

                    st.session_state[
                        delete_key
                    ] = False


                if not st.session_state[
                    delete_key
                ]:

                    if st.button(
                        "🗑️ Delete User",
                        key=f"del_btn_{uid}"
                    ):

                        st.session_state[
                            delete_key
                        ] = True

                        st.rerun()


                else:

                    st.warning(
                        "You are about to permanently "
                        "delete this user. "
                        "This action cannot be undone."
                    )


                    cols2 = st.columns(
                        [1, 1, 2]
                    )


                    with cols2[0]:

                        if st.button(
                            "Confirm Delete",
                            key=f"confirm_del_{uid}"
                        ):

                            try:

                                # Do not allow the active
                                # admin account to be deleted

                                if (
                                    uname
                                    == st.session_state.user_name
                                ):

                                    st.error(
                                        "You cannot delete "
                                        "the account currently "
                                        "logged in."
                                    )

                                else:

                                    # Remove teacher assignments

                                    if urole == "teacher":

                                        cursor.execute(
                                            """
                                            DELETE FROM
                                            teacher_subjects
                                            WHERE teacher_username=?
                                            """,
                                            (uname,)
                                        )


                                    # Remove parent link

                                    if urole == "parent":

                                        cursor.execute(
                                            """
                                            UPDATE users
                                            SET student_id=NULL
                                            WHERE id=?
                                            """,
                                            (uid,)
                                        )


                                    # Delete notifications
                                    # sent by this user

                                    cursor.execute(
                                        """
                                        DELETE FROM notifications
                                        WHERE sender_username=?
                                        """,
                                        (uname,)
                                    )


                                    # Delete user

                                    cursor.execute(
                                        """
                                        DELETE FROM users
                                        WHERE id=?
                                        """,
                                        (uid,)
                                    )

                                    conn.commit()

                                    st.session_state[
                                        delete_key
                                    ] = False

                                    st.success(
                                        f"User {uname} deleted."
                                    )

                                    st.rerun()


                            except Exception as e:

                                st.error(
                                    f"Error deleting user: {e}"
                                )


                    with cols2[1]:

                        if st.button(
                            "Cancel",
                            key=f"cancel_del_{uid}"
                        ):

                            st.session_state[
                                delete_key
                            ] = False

                            st.rerun()


                    with cols2[2]:

                        st.info(
                            "Student records are preserved. "
                            "Teacher subject assignments are "
                            "removed when a teacher is deleted."
                        )


# ============================================================
# END OF FILE
# ============================================================












