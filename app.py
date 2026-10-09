import base64
import re
from difflib import SequenceMatcher

from flask import (
    Flask, render_template, request, redirect, url_for, session, flash,
    send_from_directory
)
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "student-records-project-secret"
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024


# ============================================================
# STATIC CHOICES
# ============================================================

COURSES = ["BSCS", "BSBA", "BSEd", "BSCrim", "BSSW"]
YEAR_LEVELS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]

# Full program names shown on grade records and schedules.
PROGRAMS = {
    "BSCS": "Bachelor of Science in Computer Science",
    "BSBA": "Bachelor of Science in Business Administration",
    "BSEd": "Bachelor of Science in Education",
    "BSCrim": "Bachelor of Science in Criminology",
    "BSSW": "Bachelor of Science in Social Work"
}

ACADEMIC_PERIODS = [
    "1st Semester (2026-2027)",
    "2nd Semester (2026-2027)"
]

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

STUDENT_ID_PATTERN = re.compile(r"^\d{6}$")


# ============================================================
# TEMPORARY STORAGE
# No database is used.
# Data resets when Flask is restarted.
# ============================================================

# ONLY the administrator exists at the beginning.
# Students and teachers are added through Sign Up.
users = [
    {
        "id": 1,
        "name": "System Administrator",
        "email": "admin@school.com",
        "username": "admin",
        "password": generate_password_hash("admin123"),
        "role": "admin",
        "student_id": "",
        "course": "",
        "year_level": ""
    }
]

# No sample grades.
# Each grade: student_id, subject, grade, semester (academic period),
#             year_level, program
grades = []

# Class schedules added by teachers for students in their assignments.
# Each schedule: student_id, subject, day, time, room
schedules = []

# First real student/teacher will receive ID 2.
next_user_id = 2

# Temporary bug/contact reports (visible to the admin).
bug_reports = []

# School announcements. Only the administrator can post or remove these.
announcements = []


# ============================================================
# OOP
# ============================================================

class User:
    """Base class for all users."""

    def __init__(self, name, email, username, role):
        self.name = name
        self.email = email
        self.username = username
        self.role = role

    def dashboard_message(self):
        return "Welcome to the Student Records System."


class Student(User):
    """Student inherits from User."""

    def dashboard_message(self):
        return "View your personal grades and academic records."


class Teacher(User):
    """Teacher inherits from User."""

    def dashboard_message(self):
        return "View and manage the students in your assigned courses and year levels."


class Admin(User):
    """Admin inherits from User."""

    def dashboard_message(self):
        return "View registered users and system information."


def create_user_object(user):
    """Return the correct OOP object based on the user's role."""

    if user is None:
        return None

    classes = {
        "student": Student,
        "teacher": Teacher,
        "admin": Admin
    }

    user_class = classes.get(user["role"], User)

    return user_class(
        user["name"],
        user["email"],
        user["username"],
        user["role"]
    )


# ============================================================
# FUNCTIONS / HELPERS
# ============================================================

def find_user_by_username(username):
    for user in users:
        if user["username"].lower() == username.lower():
            return user
    return None


def find_user_by_login(login):
    """Find a user by username OR email address (used on the login page)."""
    login = login.strip().lower()
    for user in users:
        if user["username"].lower() == login or user["email"].lower() == login:
            return user
    return None


def find_user_by_id(user_id):
    for user in users:
        if user["id"] == user_id:
            return user
    return None


def get_students():
    return [user for user in users if user["role"] == "student"]


def get_teachers():
    return [user for user in users if user["role"] == "teacher"]


def get_user_grades(user_id):
    return [grade for grade in grades if grade["student_id"] == user_id]


def get_user_schedule(user_id):
    return [s for s in schedules if s["student_id"] == user_id]


def program_of(course):
    return PROGRAMS.get(course, "")


def course_of_program(program):
    """Reverse lookup: full program name -> course code."""
    for course, name in PROGRAMS.items():
        if name == program:
            return course
    return ""


# ------------------------------------------------------------
# Teacher assignments (set by the admin)
# Each assignment: {"course": "BSCS", "year_level": "2nd Year"}
# A teacher may have as many as the admin gives them.
# ------------------------------------------------------------

def get_teacher_assignments(teacher):
    return teacher.get("assignments", [])


def teacher_has_assignment(teacher, course, year_level):
    for a in get_teacher_assignments(teacher):
        if a["course"] == course and a["year_level"] == year_level:
            return True
    return False


def teacher_can_access_student(teacher, student):
    """A teacher may only touch students whose course AND year level
    match one of the teacher's assignments."""
    return teacher_has_assignment(
        teacher, student.get("course"), student.get("year_level")
    )


def grade_in_teacher_scope(teacher, grade):
    """A teacher may only edit grades recorded under a course + year level
    they are assigned to."""
    return teacher_has_assignment(
        teacher,
        course_of_program(grade.get("program", "")),
        grade.get("year_level", "")
    )


def get_teacher_students(teacher):
    return [
        s for s in get_students()
        if teacher_can_access_student(teacher, s)
    ]


def assigned_courses(teacher):
    """Assigned courses, in the standard course order, without duplicates."""
    have = {a["course"] for a in get_teacher_assignments(teacher)}
    return [c for c in COURSES if c in have]


def assigned_years(teacher):
    """Assigned year levels, in the standard order, without duplicates."""
    have = {a["year_level"] for a in get_teacher_assignments(teacher)}
    return [y for y in YEAR_LEVELS if y in have]


def load_scoped_student(student_id):
    """
    Loads the logged-in teacher and the requested student.
    Returns (teacher, student). student is None (with a flashed message)
    when the student does not exist or is outside the teacher's assignments.
    """
    teacher = find_user_by_id(session["user_id"])
    student = find_user_by_id(student_id)

    if not student or student["role"] != "student":
        flash("Student not found.", "danger")
        return teacher, None

    if not teacher_can_access_student(teacher, student):
        flash(
            "You are not assigned to this student's course and year level.",
            "danger"
        )
        return teacher, None

    return teacher, student


def student_id_taken(student_id, exclude_user_id=None):
    """Check whether a 6-digit Student ID is already registered."""
    for existing_user in users:
        if existing_user.get("student_id") == student_id:
            if exclude_user_id is not None and existing_user["id"] == exclude_user_id:
                continue
            return True
    return False


def passwords_too_similar(current_password, new_password):
    """
    Returns True if the new password is basically the old password
    wearing a disguise (identical, one contained in the other, or a
    high similarity ratio).
    """
    a = current_password.lower().strip()
    b = new_password.lower().strip()

    if not a or not b:
        return False

    if a == b:
        return True

    if a in b or b in a:
        return True

    ratio = SequenceMatcher(None, a, b).ratio()
    return ratio >= 0.7


def filter_students_for_teacher(teacher, args):
    """
    Applies the teacher's search/filter controls on top of the students
    inside the teacher's assignments.
    """
    selected_course = args.get("course", "all")
    selected_year = args.get("year_level", "all")
    student_id_search = args.get("student_id_search", "").strip()

    result = get_teacher_students(teacher)

    if selected_course and selected_course != "all":
        result = [s for s in result if s.get("course") == selected_course]

    if selected_year and selected_year != "all":
        result = [s for s in result if s.get("year_level") == selected_year]

    if student_id_search:
        result = [s for s in result if student_id_search in s.get("student_id", "")]

    return result, selected_course, selected_year, student_id_search


def email_taken(email):
    """Login accepts an email address, so emails must be unique too."""
    email = email.strip().lower()
    return any(u["email"].lower() == email for u in users)


def create_account_from_form(form):
    """
    Validate the account form (shared by public Sign Up and the admin's
    Add User page), then append the new account to `users`.

    Returns the new user dict. Raises ValueError with a friendly message
    when something is wrong, so callers just flash it.
    """
    global next_user_id

    name = form.get("name", "").strip()
    email = form.get("email", "").strip()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    role = form.get("role", "").strip().lower()
    student_id = form.get("student_id", "").strip()
    year_level = form.get("year_level", "").strip()
    course = form.get("course", "").strip()

    if not name or not email or not username or not password:
        raise ValueError("Please fill in all required fields.")

    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    if role not in ("student", "teacher"):
        raise ValueError("Please select Student or Teacher.")

    if find_user_by_username(username):
        raise ValueError("Username is already taken.")

    if email_taken(email):
        raise ValueError("Email address is already registered.")

    if role == "student":
        if not student_id:
            raise ValueError("Student ID is required for students.")

        if not STUDENT_ID_PATTERN.fullmatch(student_id):
            raise ValueError("Student ID must be exactly 6 digits.")

        if not year_level:
            raise ValueError("Please select the year level.")

        if year_level not in YEAR_LEVELS:
            raise ValueError("Please select a valid year level.")

        if course not in COURSES:
            raise ValueError("Please select a valid course.")

        # Prevent duplicate student IDs.
        if student_id_taken(student_id):
            raise ValueError("Student ID is already registered.")

    else:
        # Teachers do not choose a course. The administrator
        # assigns their courses and year levels after the account exists.
        student_id = ""
        year_level = ""
        course = ""

    new_user = {
        "id": next_user_id,
        "name": name,
        "email": email,
        "username": username,
        "password": generate_password_hash(password),
        "role": role,
        "student_id": student_id,
        "year_level": year_level,
        "course": course
    }

    if role == "teacher":
        # Course + year level pairs assigned by the admin.
        new_user["assignments"] = []

    users.append(new_user)
    next_user_id += 1

    return new_user


# ============================================================
# LOGIN / ROLE PROTECTION
# ============================================================

def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))

        # Also check that the logged-in user still exists.
        user = find_user_by_id(session["user_id"])

        if user is None:
            session.clear()
            flash("Your session is no longer valid. Please log in again.", "warning")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))

            user = find_user_by_id(session["user_id"])

            if not user:
                session.clear()
                flash("Your session is no longer valid. Please log in again.", "warning")
                return redirect(url_for("login"))

            if user["role"] not in roles:
                flash("You do not have permission to access that page.", "danger")
                return redirect(url_for("dashboard"))

            return view(*args, **kwargs)

        return wrapped_view

    return decorator


@app.context_processor
def inject_current_user():
    user_id = session.get("user_id")
    current = find_user_by_id(user_id) if user_id else None
    return {
        "current_user": current,
        "COURSES": COURSES,
        "YEAR_LEVELS": YEAR_LEVELS,
        "PROGRAMS": PROGRAMS,
        "ACADEMIC_PERIODS": ACADEMIC_PERIODS,
        "DAYS": DAYS,
        "announcements": announcements
    }


# ============================================================
# MAIN PAGES
# ============================================================

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            create_account_from_form(request.form)

            flash("Account created successfully. You can now log in.", "success")
            return redirect(url_for("login"))

        except ValueError as error:
            flash(str(error), "danger")

        except Exception:
            flash("Something went wrong while creating the account.", "danger")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        login_input = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Users can sign in with either their username or their email address.
        user = find_user_by_login(login_input)

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]

            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username/email or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ============================================================
# INSTALLABLE APP (PWA): manifest, service worker, offline page
# Lets Acadex be installed on PC (Chrome/Edge) and phones
# (Android Chrome, iPhone/iPad Safari "Add to Home Screen").
# ============================================================

@app.route("/manifest.webmanifest")
def web_manifest():
    response = send_from_directory(
        app.static_folder, "manifest.webmanifest",
        mimetype="application/manifest+json"
    )
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.route("/sw.js")
def service_worker():
    # Served from the site root so the worker can control every page.
    response = send_from_directory(
        app.static_folder, "sw.js", mimetype="application/javascript"
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Service-Worker-Allowed"] = "/"
    return response


@app.route("/offline")
def offline():
    return render_template("offline.html")


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
@login_required
def dashboard():
    user = find_user_by_id(session["user_id"])

    # This prevents the NoneType error.
    if user is None:
        session.clear()
        flash("Your session is no longer valid. Please log in again.", "warning")
        return redirect(url_for("login"))

    user_object = create_user_object(user)

    if user["role"] == "student":
        return render_template(
            "student_dashboard.html",
            user=user,
            message=user_object.dashboard_message()
        )

    if user["role"] == "teacher":
        students, selected_course, selected_year, student_id_search = filter_students_for_teacher(
            user, request.args
        )

        return render_template(
            "teacher_dashboard.html",
            user=user,
            message=user_object.dashboard_message(),
            students=students,
            selected_course=selected_course,
            selected_year=selected_year,
            student_id_search=student_id_search,
            assignments=get_teacher_assignments(user),
            assigned_course_options=assigned_courses(user),
            assigned_year_options=assigned_years(user)
        )

    # Admin dashboard.
    return render_template(
        "admin_dashboard.html",
        user=user,
        message=user_object.dashboard_message(),
        users=users,
        students=get_students(),
        teachers=get_teachers(),
        bug_reports=bug_reports
    )


# ============================================================
# STUDENT: ACADEMIC RECORDS (GRADES)
# ============================================================

@app.route("/academic-records")
@role_required("student")
def academic_records():
    user = find_user_by_id(session["user_id"])

    return render_template(
        "academic_records.html",
        user=user,
        my_grades=get_user_grades(user["id"])
    )


# ============================================================
# STUDENT: SCHEDULE
# ============================================================

@app.route("/schedule")
@role_required("student")
def student_schedule():
    user = find_user_by_id(session["user_id"])

    my_schedule = sorted(
        get_user_schedule(user["id"]),
        key=lambda s: (DAYS.index(s["day"]) if s["day"] in DAYS else 7, s["time"])
    )

    return render_template(
        "schedule.html",
        user=user,
        my_schedule=my_schedule
    )


# ============================================================
# TEACHER: MY STUDENTS (students inside the teacher's assignments)
# ============================================================

@app.route("/teacher/students")
@role_required("teacher")
def teacher_students():
    teacher = find_user_by_id(session["user_id"])

    return render_template(
        "teacher_students.html",
        user=teacher,
        my_students=get_teacher_students(teacher),
        assignments=get_teacher_assignments(teacher)
    )


# ============================================================
# TEACHER: GRADES
# ============================================================

@app.route("/teacher/student/<int:student_id>/grades", methods=["GET", "POST"])
@role_required("teacher")
def manage_grades(student_id):
    teacher, student = load_scoped_student(student_id)

    if student is None:
        return redirect(url_for("teacher_students"))

    if request.method == "POST":
        try:
            subject = request.form.get("subject", "").strip()
            grade = request.form.get("grade", "").strip()
            semester = request.form.get("semester", "").strip()
            year_level = request.form.get("year_level", "").strip()
            program = request.form.get("program", "").strip()

            if not subject or not grade:
                raise ValueError("Subject and grade are required.")

            numeric_grade = float(grade)

            if numeric_grade < 1.00 or numeric_grade > 5.00:
                raise ValueError("Grade must be between 1.00 and 5.00.")

            if semester not in ACADEMIC_PERIODS:
                raise ValueError("Please select a valid academic period.")

            if year_level not in YEAR_LEVELS:
                raise ValueError("Please select a valid year level.")

            if program not in PROGRAMS.values():
                raise ValueError("Please select a valid program.")

            # The program + year level must be one the teacher is assigned to.
            if not teacher_has_assignment(
                teacher, course_of_program(program), year_level
            ):
                raise ValueError(
                    "You are not assigned to teach that program and year level."
                )

            grades.append({
                "student_id": student_id,
                "subject": subject,
                "grade": f"{numeric_grade:.2f}",
                "semester": semester,
                "year_level": year_level,
                "program": program
            })

            flash("Grade added successfully.", "success")
            return redirect(url_for("manage_grades", student_id=student_id))

        except ValueError as error:
            flash(str(error), "danger")

        except Exception:
            flash("Invalid grade input.", "danger")

    # Each row keeps its real index so update/delete hit the right grade,
    # plus a flag for whether this teacher may edit it.
    grade_rows = []
    for index, g in enumerate(get_user_grades(student_id)):
        row = dict(g)
        row["index"] = index
        row["editable"] = grade_in_teacher_scope(teacher, g)
        grade_rows.append(row)

    allowed_years = assigned_years(teacher)
    allowed_programs = [(c, PROGRAMS[c]) for c in assigned_courses(teacher)]

    return render_template(
        "manage_grades.html",
        student=student,
        student_grades=grade_rows,
        student_program=program_of(student.get("course", "")),
        allowed_years=allowed_years,
        allowed_programs=allowed_programs
    )


@app.route(
    "/teacher/grade/update/<int:student_id>/<int:grade_index>",
    methods=["POST"]
)
@role_required("teacher")
def update_grade(student_id, grade_index):
    teacher, student = load_scoped_student(student_id)

    if student is None:
        return redirect(url_for("teacher_students"))

    student_grades = get_user_grades(student_id)

    try:
        target = student_grades[grade_index]

        if not grade_in_teacher_scope(teacher, target):
            flash(
                "You are not assigned to this grade's program and year level.",
                "danger"
            )
            return redirect(url_for("manage_grades", student_id=student_id))

        subject = request.form.get("subject", "").strip()
        grade_value = request.form.get("grade", "").strip()

        if not subject or not grade_value:
            raise ValueError("Subject and grade are required.")

        numeric_grade = float(grade_value)

        if numeric_grade < 1.00 or numeric_grade > 5.00:
            raise ValueError("Grade must be between 1.00 and 5.00.")

        target["subject"] = subject
        target["grade"] = f"{numeric_grade:.2f}"

        flash("Grade updated successfully.", "success")

    except (IndexError, ValueError):
        flash(
            "The grade could not be updated. Use a grade from 1.00 to 5.00.",
            "danger"
        )

    return redirect(url_for("manage_grades", student_id=student_id))


@app.route(
    "/teacher/grade/delete/<int:student_id>/<int:grade_index>",
    methods=["POST"]
)
@role_required("teacher")
def delete_grade(student_id, grade_index):
    teacher, student = load_scoped_student(student_id)

    if student is None:
        return redirect(url_for("teacher_students"))

    student_grades = get_user_grades(student_id)

    try:
        target = student_grades[grade_index]

        if not grade_in_teacher_scope(teacher, target):
            flash(
                "You are not assigned to this grade's program and year level.",
                "danger"
            )
            return redirect(url_for("manage_grades", student_id=student_id))

        grades.remove(target)

        flash("Grade deleted.", "success")

    except (IndexError, ValueError):
        flash("Grade could not be deleted.", "danger")

    return redirect(url_for("manage_grades", student_id=student_id))


# ============================================================
# TEACHER: SCHEDULES
# ============================================================

@app.route("/teacher/student/<int:student_id>/schedule", methods=["GET", "POST"])
@role_required("teacher")
def manage_schedule(student_id):
    teacher, student = load_scoped_student(student_id)

    if student is None:
        return redirect(url_for("teacher_students"))

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        day = request.form.get("day", "").strip()
        time = request.form.get("time", "").strip()
        room = request.form.get("room", "").strip()

        if not subject or not day or not time or not room:
            flash("Subject, day, time, and room are all required.", "danger")
        elif day not in DAYS:
            flash("Please select a valid day.", "danger")
        else:
            schedules.append({
                "student_id": student_id,
                "subject": subject,
                "day": day,
                "time": time,
                "room": room
            })
            flash("Schedule entry added.", "success")
            return redirect(url_for("manage_schedule", student_id=student_id))

    student_schedule = sorted(
        get_user_schedule(student_id),
        key=lambda s: (DAYS.index(s["day"]) if s["day"] in DAYS else 7, s["time"])
    )

    return render_template(
        "teacher_schedule.html",
        student=student,
        student_schedule=student_schedule
    )


@app.route(
    "/teacher/schedule/delete/<int:student_id>/<int:schedule_index>",
    methods=["POST"]
)
@role_required("teacher")
def delete_schedule(student_id, schedule_index):
    teacher, student = load_scoped_student(student_id)

    if student is None:
        return redirect(url_for("teacher_students"))

    student_schedules = get_user_schedule(student_id)

    try:
        target = student_schedules[schedule_index]
        schedules.remove(target)
        flash("Schedule entry deleted.", "success")
    except (IndexError, ValueError):
        flash("Schedule entry could not be deleted.", "danger")

    return redirect(url_for("manage_schedule", student_id=student_id))


# ============================================================
# CLASSMATES (STUDENT)
# ============================================================

@app.route("/classmates")
@role_required("student")
def classmates():
    user = find_user_by_id(session["user_id"])

    classmate_list = [
        s for s in get_students()
        if s["id"] != user["id"]
        and s.get("course") == user.get("course")
        and s.get("year_level") == user.get("year_level")
    ]

    return render_template("classmates.html", user=user, classmates=classmate_list)


# ============================================================
# PROFILE
# ============================================================

@app.route("/profile")
@login_required
def profile():
    user = find_user_by_id(session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template("profile.html", user=user)


ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_AVATAR_BYTES = 2 * 1024 * 1024


@app.route("/profile/avatar", methods=["POST"])
@login_required
def update_avatar():
    user = find_user_by_id(session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    if request.form.get("action") == "remove":
        user["avatar"] = ""
        flash("Profile picture removed.", "success")
        return redirect(url_for("profile"))

    file = request.files.get("avatar")

    if file is None or file.filename == "":
        flash("Please choose an image to upload.", "error")
        return redirect(url_for("profile"))

    if file.mimetype not in ALLOWED_AVATAR_TYPES:
        flash("Profile picture must be a PNG, JPG, GIF, or WEBP image.", "error")
        return redirect(url_for("profile"))

    data = file.read()

    if len(data) > MAX_AVATAR_BYTES:
        flash("Profile picture must be 2 MB or smaller.", "error")
        return redirect(url_for("profile"))

    # Stored in memory like the rest of the app's data.
    encoded = base64.b64encode(data).decode("ascii")
    user["avatar"] = f"data:{file.mimetype};base64,{encoded}"
    flash("Profile picture updated.", "success")
    return redirect(url_for("profile"))


# ============================================================
# SETTINGS (client-side preferences only, e.g. Dark Mode)
# ============================================================

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html")


# ============================================================
# CONTACT / BUG REPORT
# ============================================================

@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not subject or not message:
            flash("Please complete all fields before submitting.", "danger")

        else:
            bug_reports.append({
                "name": name,
                "email": email,
                "subject": subject,
                "message": message
            })

            flash(
                "Your report has been submitted to the school system administrator.",
                "success"
            )

            return redirect(url_for("contact"))

    return render_template("contact.html")


# ============================================================
# PASSWORD CHANGE
# ============================================================

@app.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    user = find_user_by_id(session["user_id"])

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not check_password_hash(user["password"], current_password):
            flash("Current password is incorrect.", "danger")

        elif len(new_password) < 6:
            flash("New password must be at least 6 characters.", "danger")

        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")

        elif passwords_too_similar(current_password, new_password):
            flash(
                "Your new password is too similar to your current password. "
                "Please choose a password that is clearly different.",
                "danger"
            )

        else:
            user["password"] = generate_password_hash(new_password)

            flash("Password changed successfully.", "success")
            return redirect(url_for("dashboard"))

    return render_template("change_password.html")


# ============================================================
# ADMIN: ADD A STUDENT OR TEACHER ACCOUNT
# ============================================================

@app.route("/admin/add-user", methods=["GET", "POST"])
@role_required("admin")
def admin_add_user():
    # ?role=teacher / ?role=student pre-selects the account type.
    preselect = request.args.get("role", "student")
    if preselect not in ("student", "teacher"):
        preselect = "student"

    if request.method == "POST":
        try:
            new_user = create_account_from_form(request.form)

            if new_user["role"] == "teacher":
                flash(
                    f"Teacher account for {new_user['name']} was created. "
                    "Now assign the courses and year levels they handle.",
                    "success"
                )
                return redirect(
                    url_for("admin_teacher_assignments", user_id=new_user["id"])
                )

            flash(f"Student account for {new_user['name']} was created.", "success")
            return redirect(url_for("dashboard"))

        except ValueError as error:
            flash(str(error), "danger")
            # Keep what the admin typed (never the password).
            preselect = request.form.get("role", preselect)

        except Exception:
            flash("Something went wrong while creating the account.", "danger")

    return render_template(
        "admin_add_user.html",
        form=request.form if request.method == "POST" else {},
        preselect=preselect
    )


# ============================================================
# ADMIN: RESET A STUDENT'S OR TEACHER'S PASSWORD
# ============================================================

@app.route("/admin/reset-password/<int:user_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_reset_password(user_id):
    target = find_user_by_id(user_id)

    if not target or target["role"] not in ("student", "teacher"):
        flash("Only student and teacher accounts can be reset from this page.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(new_password) < 6:
            flash("New password must be at least 6 characters.", "danger")

        elif new_password != confirm_password:
            flash("New passwords do not match.", "danger")

        else:
            target["password"] = generate_password_hash(new_password)
            flash(f"Password for {target['name']} has been reset.", "success")
            return redirect(url_for("dashboard"))

    return render_template("admin_reset_password.html", target=target)


# ============================================================
# ADMIN: CHANGE A STUDENT'S ID
# ============================================================

@app.route("/admin/change-id/<int:user_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_change_id(user_id):
    target = find_user_by_id(user_id)

    if not target or target["role"] != "student":
        flash("Only student accounts can have their ID changed here.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        new_student_id = request.form.get("new_student_id", "").strip()

        if not STUDENT_ID_PATTERN.fullmatch(new_student_id):
            flash("Student ID must be exactly 6 digits.", "danger")

        elif student_id_taken(new_student_id, exclude_user_id=target["id"]):
            flash("That Student ID is already registered to another account.", "danger")

        else:
            old_id = target["student_id"]
            target["student_id"] = new_student_id
            flash(
                f"Student ID changed from {old_id} to {new_student_id} "
                f"for {target['name']}.",
                "success"
            )
            return redirect(url_for("dashboard"))

    return render_template("admin_change_id.html", target=target)


# ============================================================
# ADMIN: DELETE A STUDENT OR TEACHER ACCOUNT
# ============================================================

@app.route("/admin/delete-account/<int:user_id>", methods=["POST"])
@role_required("admin")
def admin_delete_account(user_id):
    target = find_user_by_id(user_id)

    # The admin account itself can never be deleted.
    if not target or target["role"] == "admin":
        flash("That account cannot be deleted.", "danger")
        return redirect(url_for("dashboard"))

    users.remove(target)

    # Remove the account's grades and schedules too.
    grades[:] = [
        grade for grade in grades
        if grade["student_id"] != user_id
    ]
    schedules[:] = [
        item for item in schedules
        if item["student_id"] != user_id
    ]

    flash(f"Account for {target['name']} ({target['role']}) was deleted.", "success")
    return redirect(url_for("dashboard"))


# ============================================================
# ADMIN: CHANGE AN ACCOUNT'S ROLE (student <-> teacher)
# ============================================================

@app.route("/admin/change-role/<int:user_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_change_role(user_id):
    target = find_user_by_id(user_id)

    if not target or target["role"] == "admin":
        flash("Only student and teacher accounts can have their role changed.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        new_role = request.form.get("role", "").strip().lower()

        if new_role not in ("student", "teacher"):
            flash("Please choose Student or Teacher.", "danger")

        elif new_role == target["role"]:
            flash("This account already has that role.", "warning")

        elif new_role == "teacher":
            # Student -> Teacher: clear student-only fields.
            # The admin assigns their courses and year levels afterwards.
            target["role"] = "teacher"
            target["student_id"] = ""
            target["year_level"] = ""
            target["course"] = ""
            target["assignments"] = []
            flash(
                f"{target['name']} is now a Teacher. "
                "Assign their courses and year levels from the dashboard.",
                "success"
            )
            return redirect(url_for("dashboard"))

        else:
            # Teacher -> Student: student details are required.
            new_student_id = request.form.get("new_student_id", "").strip()
            year_level = request.form.get("year_level", "").strip()
            course = request.form.get("course", "").strip()

            if not STUDENT_ID_PATTERN.fullmatch(new_student_id):
                flash("Student ID must be exactly 6 digits.", "danger")

            elif student_id_taken(new_student_id, exclude_user_id=target["id"]):
                flash("That Student ID is already registered to another account.", "danger")

            elif year_level not in YEAR_LEVELS:
                flash("Please select a valid year level.", "danger")

            elif course not in COURSES:
                flash("Please select a valid course.", "danger")

            else:
                target["role"] = "student"
                target["student_id"] = new_student_id
                target["year_level"] = year_level
                target["course"] = course
                target.pop("assignments", None)
                flash(f"{target['name']} is now a Student.", "success")
                return redirect(url_for("dashboard"))

    return render_template("admin_change_role.html", target=target)


# ============================================================
# ADMIN: TEACHER ASSIGNMENTS (course + year level)
# ============================================================

@app.route("/admin/teacher/<int:user_id>/assignments", methods=["GET", "POST"])
@role_required("admin")
def admin_teacher_assignments(user_id):
    target = find_user_by_id(user_id)

    if not target or target["role"] != "teacher":
        flash("Assignments can only be managed for teacher accounts.", "danger")
        return redirect(url_for("dashboard"))

    assignments = target.setdefault("assignments", [])

    if request.method == "POST":
        course = request.form.get("course", "").strip()
        year_level = request.form.get("year_level", "").strip()

        if course not in COURSES:
            flash("Please select a valid course.", "danger")

        elif year_level not in YEAR_LEVELS:
            flash("Please select a valid year level.", "danger")

        elif teacher_has_assignment(target, course, year_level):
            flash(
                f"{target['name']} is already assigned to {course} - {year_level}.",
                "warning"
            )

        else:
            assignments.append({"course": course, "year_level": year_level})
            flash(
                f"{target['name']} was assigned to {course} - {year_level}.",
                "success"
            )
            return redirect(
                url_for("admin_teacher_assignments", user_id=user_id)
            )

    return render_template(
        "admin_teacher_assignments.html",
        target=target,
        assignments=assignments
    )


@app.route(
    "/admin/teacher/<int:user_id>/assignments/delete/<int:assignment_index>",
    methods=["POST"]
)
@role_required("admin")
def admin_delete_teacher_assignment(user_id, assignment_index):
    target = find_user_by_id(user_id)

    if not target or target["role"] != "teacher":
        flash("Assignments can only be managed for teacher accounts.", "danger")
        return redirect(url_for("dashboard"))

    try:
        removed = target.get("assignments", []).pop(assignment_index)
        flash(
            f"Removed {removed['course']} - {removed['year_level']} "
            f"from {target['name']}.",
            "success"
        )
    except IndexError:
        flash("Assignment not found.", "danger")

    return redirect(url_for("admin_teacher_assignments", user_id=user_id))


# ============================================================
# ADMIN: VIEW / DELETE BUG REPORTS
# ============================================================

@app.route("/admin/report/delete/<int:report_index>", methods=["POST"])
@role_required("admin")
def admin_delete_report(report_index):
    try:
        bug_reports.pop(report_index)
        flash("Report removed.", "success")
    except IndexError:
        flash("Report not found.", "danger")

    return redirect(url_for("dashboard"))


# ============================================================
# ADMIN: ANNOUNCEMENTS
# ============================================================

@app.route("/admin/announcement/add", methods=["POST"])
@role_required("admin")
def admin_add_announcement():
    title = request.form.get("title", "").strip()
    body = request.form.get("body", "").strip()

    if not title or not body:
        flash("Announcement title and message are both required.", "danger")
    else:
        announcements.append({
            "title": title,
            "body": body
        })
        flash("Announcement posted for all users.", "success")

    return redirect(url_for("dashboard"))


@app.route("/admin/announcement/delete/<int:announcement_index>", methods=["POST"])
@role_required("admin")
def admin_delete_announcement(announcement_index):
    try:
        announcements.pop(announcement_index)
        flash("Announcement removed.", "success")
    except IndexError:
        flash("Announcement not found.", "danger")

    return redirect(url_for("dashboard"))


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("RENDER") is None)
