import re
from difflib import SequenceMatcher

from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "student-records-project-secret"


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

# Class schedules added by teachers for their selected students.
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
        return "View students and manage their grades."


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


def get_teacher_students(teacher_id):
    """Students the teacher has selected to handle (any course)."""
    return [
        s for s in get_students()
        if teacher_id in s.get("teacher_ids", [])
    ]


def get_available_students(teacher_id):
    """Students the teacher has NOT selected yet."""
    return [
        s for s in get_students()
        if teacher_id not in s.get("teacher_ids", [])
    ]


def program_of(course):
    return PROGRAMS.get(course, "")


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
    Applies the teacher's search/filter controls on top of the full
    student list. Defaults to the teacher's own handled course.
    """
    selected_course = args.get("course", teacher.get("course", "") or "all")
    selected_year = args.get("year_level", "all")
    student_id_search = args.get("student_id_search", "").strip()

    result = get_students()

    if selected_course and selected_course != "all":
        result = [s for s in result if s.get("course") == selected_course]

    if selected_year and selected_year != "all":
        result = [s for s in result if s.get("year_level") == selected_year]

    if student_id_search:
        result = [s for s in result if student_id_search in s.get("student_id", "")]

    return result, selected_course, selected_year, student_id_search


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
    global next_user_id

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            role = request.form.get("role", "").strip().lower()
            student_id = request.form.get("student_id", "").strip()
            year_level = request.form.get("year_level", "").strip()
            course = request.form.get("course", "").strip()

            if not name or not email or not username or not password:
                raise ValueError("Please fill in all required fields.")

            if len(password) < 6:
                raise ValueError("Password must be at least 6 characters.")

            # Public sign-up is only for students and teachers.
            if role not in ("student", "teacher"):
                raise ValueError("Please select Student or Teacher.")

            if find_user_by_username(username):
                raise ValueError("Username is already taken.")

            if role == "student":
                if not student_id:
                    raise ValueError("Student ID is required for students.")

                if not STUDENT_ID_PATTERN.fullmatch(student_id):
                    raise ValueError("Student ID must be exactly 6 digits.")

                if not year_level:
                    raise ValueError("Please select your year level.")

                if course not in COURSES:
                    raise ValueError("Please select a valid course.")

                # Prevent duplicate student IDs.
                if student_id_taken(student_id):
                    raise ValueError("Student ID is already registered.")

            else:
                # Teachers register the course they handle, not a student ID.
                if course not in COURSES:
                    raise ValueError("Please select the course you handle.")

                student_id = ""
                year_level = ""

            new_user = {
                "id": next_user_id,
                "name": name,
                "email": email,
                "username": username,
                "password": generate_password_hash(password),
                "role": role,
                "student_id": student_id,
                "year_level": year_level,
                "course": course,
                # Teachers who selected this student (their IDs).
                "teacher_ids": []
            }

            users.append(new_user)
            next_user_id += 1

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
            student_id_search=student_id_search
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
# TEACHER: MY STUDENTS (selected students, any course)
# ============================================================

@app.route("/teacher/students")
@role_required("teacher")
def teacher_students():
    teacher = find_user_by_id(session["user_id"])

    return render_template(
        "teacher_students.html",
        user=teacher,
        my_students=get_teacher_students(teacher["id"]),
        available_students=get_available_students(teacher["id"])
    )


@app.route("/teacher/student/select/<int:student_id>", methods=["POST"])
@role_required("teacher")
def select_student(student_id):
    teacher = find_user_by_id(session["user_id"])
    student = find_user_by_id(student_id)

    if not student or student["role"] != "student":
        flash("Student not found.", "danger")
        return redirect(url_for("teacher_students"))

    teacher_ids = student.setdefault("teacher_ids", [])

    if teacher["id"] in teacher_ids:
        flash(f"{student['name']} is already in your students list.", "warning")
    else:
        teacher_ids.append(teacher["id"])
        flash(f"{student['name']} was added to your students list.", "success")

    return redirect(url_for("teacher_students"))


@app.route("/teacher/student/unselect/<int:student_id>", methods=["POST"])
@role_required("teacher")
def unselect_student(student_id):
    teacher = find_user_by_id(session["user_id"])
    student = find_user_by_id(student_id)

    if student and teacher["id"] in student.get("teacher_ids", []):
        student["teacher_ids"].remove(teacher["id"])
        flash(f"{student['name']} was removed from your students list.", "success")

    return redirect(url_for("teacher_students"))


# ============================================================
# TEACHER: GRADES
# ============================================================

@app.route("/teacher/student/<int:student_id>/grades", methods=["GET", "POST"])
@role_required("teacher")
def manage_grades(student_id):
    student = find_user_by_id(student_id)

    if not student or student["role"] != "student":
        flash("Student not found.", "danger")
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

    return render_template(
        "manage_grades.html",
        student=student,
        student_grades=get_user_grades(student_id),
        student_program=program_of(student.get("course", ""))
    )


@app.route(
    "/teacher/grade/update/<int:student_id>/<int:grade_index>",
    methods=["POST"]
)
@role_required("teacher")
def update_grade(student_id, grade_index):
    student_grades = get_user_grades(student_id)

    try:
        target = student_grades[grade_index]

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
    student_grades = get_user_grades(student_id)

    try:
        target = student_grades[grade_index]
        grades.remove(target)

        flash("Grade deleted.", "success")

    except (IndexError, ValueError):
        flash("Grade could not be deleted.", "danger")

    return redirect(url_for("manage_grades", student_id=student_id))


# Kept for compatibility with the existing teacher template.
@app.route("/teacher/student/delete/<int:student_id>", methods=["POST"])
@role_required("teacher")
def delete_student(student_id):
    student = find_user_by_id(student_id)

    if not student or student["role"] != "student":
        flash("Student not found.", "danger")
        return redirect(url_for("dashboard"))

    users.remove(student)

    # Remove the student's grades and schedules too.
    grades[:] = [
        grade for grade in grades
        if grade["student_id"] != student_id
    ]
    schedules[:] = [
        item for item in schedules
        if item["student_id"] != student_id
    ]

    flash("Student and their records were deleted.", "success")
    return redirect(url_for("dashboard"))


# ============================================================
# TEACHER: SCHEDULES
# ============================================================

@app.route("/teacher/student/<int:student_id>/schedule", methods=["GET", "POST"])
@role_required("teacher")
def manage_schedule(student_id):
    student = find_user_by_id(student_id)

    if not student or student["role"] != "student":
        flash("Student not found.", "danger")
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
            # Student -> Teacher: clear student-only fields, keep the course.
            target["role"] = "teacher"
            target["student_id"] = ""
            target["year_level"] = ""
            flash(f"{target['name']} is now a Teacher.", "success")
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
                flash(f"{target['name']} is now a Student.", "success")
                return redirect(url_for("dashboard"))

    return render_template("admin_change_role.html", target=target)


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
