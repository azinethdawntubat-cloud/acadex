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

COURSES = ["Bachelor of Science in Computer Science", "Bachelor of Science in Business Administration", "Bachelor of Science in Education", "Bachelor of Science in Criminology", "Bachelor of Social Work", "Bachelor of Arts and English Language Studies"]
YEAR_LEVELS = ["1st Year", "2nd Year", "3rd Year", "4th Year"]

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
grades = []

# First real student/teacher will receive ID 2.
next_user_id = 2

# Temporary bug/contact reports.
bug_reports = []


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
        "YEAR_LEVELS": YEAR_LEVELS
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
            student_id = request.form.get("student_id", "").strip()
            year_level = request.form.get("year_level", "").strip()
            course = request.form.get("course", "").strip()

            if not name or not email or not username or not password:
                raise ValueError("Please fill in all required fields.")

            if len(password) < 6:
                raise ValueError("Password must be at least 6 characters.")

            if find_user_by_username(username):
                raise ValueError("Username is already taken.")

            # Public sign-up always creates a Student account.
            # Only an administrator can promote an account to Teacher.
            if not student_id:
                raise ValueError("Student ID is required.")

            if not STUDENT_ID_PATTERN.fullmatch(student_id):
                raise ValueError("Student ID must be exactly 6 digits.")

            if not year_level:
                raise ValueError("Please select your year level.")

            if course not in COURSES:
                raise ValueError("Please select a valid course.")

            # Prevent duplicate student IDs.
            for existing_user in users:
                if existing_user.get("student_id") == student_id:
                    raise ValueError("Student ID is already registered.")

            new_user = {
                "id": next_user_id,
                "name": name,
                "email": email,
                "username": username,
                "password": generate_password_hash(password),
                "role": "student",
                "student_id": student_id,
                "year_level": year_level,
                "course": course
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
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = find_user_by_username(username)

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]

            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "danger")

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
            message=user_object.dashboard_message(),
            my_grades=get_user_grades(user["id"])
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
        users=users
    )


# ============================================================
# TEACHER FUNCTIONS
# ============================================================

@app.route("/teacher/student/<int:student_id>/grades", methods=["GET", "POST"])
@role_required("teacher")
def manage_grades(student_id):
    student = find_user_by_id(student_id)

    if not student or student["role"] != "student":
        flash("Student not found.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        try:
            subject = request.form.get("subject", "").strip()
            grade = request.form.get("grade", "").strip()

            if not subject or not grade:
                raise ValueError("Subject and grade are required.")

            numeric_grade = float(grade)

            if numeric_grade < 1.00 or numeric_grade > 5.00:
                raise ValueError("Grade must be between 1.00 and 5.00.")

            grades.append({
                "student_id": student_id,
                "subject": subject,
                "grade": f"{numeric_grade:.2f}"
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
        student_grades=get_user_grades(student_id)
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

    # Remove the student's grades too.
    grades[:] = [
        grade for grade in grades
        if grade["student_id"] != student_id
    ]

    flash("Student and their grades were deleted.", "success")
    return redirect(url_for("dashboard"))


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
# ADMIN: RESET A STUDENT'S PASSWORD
# ============================================================

@app.route("/admin/reset-password/<int:user_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_reset_password(user_id):
    target = find_user_by_id(user_id)

    if not target or target["role"] != "student":
        flash("Only student accounts can be reset from this page.", "danger")
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
# ADMIN: CHANGE A USER'S ROLE
# ============================================================

@app.route("/admin/change-role/<int:user_id>", methods=["GET", "POST"])
@role_required("admin")
def admin_change_role(user_id):
    target = find_user_by_id(user_id)

    if not target or target["role"] == "admin":
        flash("That account's role cannot be changed here.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        try:
            role = request.form.get("role", "").strip().lower()
            student_id = request.form.get("student_id", "").strip()
            year_level = request.form.get("year_level", "").strip()
            course = request.form.get("course", "").strip()

            if role not in ("student", "teacher"):
                raise ValueError("Please select Student or Teacher.")

            if role == "student":
                if not student_id:
                    raise ValueError("Student ID is required for students.")

                if not STUDENT_ID_PATTERN.fullmatch(student_id):
                    raise ValueError("Student ID must be exactly 6 digits.")

                if not year_level:
                    raise ValueError("Please select a year level.")

                if course not in COURSES:
                    raise ValueError("Please select a valid course.")

                # Prevent duplicate student IDs with any other account.
                for existing_user in users:
                    if existing_user["id"] != target["id"] and existing_user.get("student_id") == student_id:
                        raise ValueError("Student ID is already registered to another user.")

            else:
                # Teachers register the course they handle, not a student ID.
                if course not in COURSES:
                    raise ValueError("Please select the course this teacher handles.")

                student_id = ""
                year_level = ""

            target["role"] = role
            target["student_id"] = student_id
            target["year_level"] = year_level
            target["course"] = course

            flash(f"{target['name']}'s role has been updated to {role.capitalize()}.", "success")
            return redirect(url_for("dashboard"))

        except ValueError as error:
            flash(str(error), "danger")

    return render_template("admin_change_role.html", target=target)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
