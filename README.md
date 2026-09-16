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

- Register (choosing Year Level, Course, and a 6-digit Student ID) — public
  sign-up always creates a Student account
- Login
- View only personal grades
- View classmates who share the same course and year level
- View personal profile
- Change password (new password must be clearly different from the current one)
- Report a system problem
- Change display settings (Dark Mode, larger text, compact tables)

## Teacher

- There is no public Teacher sign-up. An admin promotes an existing
  Student account to Teacher (see Admin section below).
- Login
- List the students they handle (filtered by their course by default)
- Search students by Course, Year Level, or Student ID
- Add grades / subjects
- Update grades
- Delete grades
- Remove students
- View personal profile
- Change password
- Report a system problem
- Change display settings

## Admin

- Default administrative account
- View registered users and their information
- Change any non-admin user's role between Student and Teacher
- Reset a student's password if they forgot their current one (no current
  password required)
- View personal profile
- Change password
- Report a system problem
- Change display settings

## Registration

Public registration always creates a Student account, and asks for a
Student ID (exactly 6 digits), Year Level, and Course. There is no role
choice on the sign-up form.

Teacher accounts are not self-registered — an admin promotes a Student
account to Teacher from the Registered Users page. Admin registration is
also intentionally disabled; the admin account is provided by the system.

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
