# Student Records Management System

A formal school-style **Python Flask + HTML/CSS** final project.

## Storage Requirement

This project follows the requirement to use **Python Lists only**.
There is NO database.

Records are temporary and reset when the Flask server restarts.
Display preferences (Dark Mode, text size, table density) are saved in the
browser's `localStorage`, since there is no database to store them in.

## Courses

- BSCS
- BSBA
- BSEd
- BSCrim
- BSSW

## Student

- Register as Student (choosing Year Level, Course, and a 6-digit Student ID)
- Login (with username OR email address)
- View only personal grades on the **Academic Records** page (top bar)
- View classmates who share the same course and year level
- View personal profile
- Change password (new password must be clearly different from the current one)
- Report a system problem
- Change display settings (Dark Mode, larger text, compact tables)

## Teacher

- Register as Teacher (choosing the Course they handle)
- Login (with username OR email address)
- **Select Students** from any course, then manage them on the **Students** page (top bar) (filtered by their course by default)
- Search students by Course, Year Level, or Student ID
- Add grades / subjects with Academic Period, Year Level, and Program (e.g. 1st Semester (2026-2027), 2nd Year, Bachelor of Science in Computer Science)
- Update grades
- Delete grades
- Remove students
- Post class schedules (subject, day, time, room) for selected students — students see these on their Schedule page
- View personal profile
- Change password
- Report a system problem
- Change display settings

## Admin

- Default administrative account
- View registered users, separated into Students and Teachers tables
- Reset a student's password if they forgot their current one (no current
  password required)
- View personal profile
- Change password
- Report a system problem
- Change display settings

## Registration

The registration form allows users to select:
- Student — includes Student ID (exactly 6 digits), Year Level, and Course
- Teacher — includes the Course they handle

Admin registration is intentionally disabled. The admin account is provided by the system.

## Default administrative account

Username: `admin`
Password: `admin123`

## How to run

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open:

`http://127.0.0.1:5000`

## Interface Notes

- Navigation is now a left sidebar (collapses into a hamburger menu on
  narrow/mobile screens).
- All password fields have a show/hide "eye" icon.
- Settings page lets each user turn on Dark Mode, larger text, and compact
  tables — saved per-browser via `localStorage`.

## OOP requirements demonstrated

- Functions
- Lists
- Encapsulation through classes
- Inheritance
- Polymorphism
- Exception Handling
- Flask
- HTML/CSS
- Role-based access control


## Recent changes

- Left sidebar removed; navigation moved to a top bar.
- Login accepts username OR email address.
- Student dashboard: Academic Records and Schedule moved to their own
  top-bar pages.
- Grades now record Academic Period, Year Level, and Program.
- Teachers select students (any course) via Select Students and manage
  them from the Students top-bar page (grades, schedules, remove).
- Admin dashboard separates Students and Teachers into two tables.
- Admin can view submitted problem reports and post announcements.
