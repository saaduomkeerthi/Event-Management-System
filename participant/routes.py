from flask import Blueprint, render_template, session, redirect, url_for, flash,request
from models.db import get_db_connection
from datetime import date
from datetime import date

today = date.today()
participant_bp = Blueprint("participant", __name__, template_folder="templates")

# ------------------------
# Participant Dashboard
# ------------------------
@participant_bp.route("/dashboard")
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get("user_id")

    # Get logged-in participant details
    cursor.execute("SELECT user_id, name, email, phone, organization, profile_picture FROM users WHERE user_id=%s", (user_id,))
    user = cursor.fetchone()

    # Total registered events (only for upcoming/future events)
    cursor.execute("""
    SELECT COUNT(*) AS registered_count
    FROM registrations r
    JOIN events e ON r.event_id = e.event_id
    WHERE r.participant_id = %s AND e.event_date >= CURDATE()
""", (user_id,))
    registered_events_count = cursor.fetchone()["registered_count"]


    # Attended events
    cursor.execute("""
        SELECT COUNT(*) AS attended_count 
        FROM registrations 
        WHERE participant_id=%s AND status='attended'
    """, (user_id,))
    attended_events_count = cursor.fetchone()["attended_count"]

    # Attendance %
    attendance_percentage = 0
    if registered_events_count > 0:
        attendance_percentage = round((attended_events_count / registered_events_count) * 100, 2)

    # Upcoming events count
    cursor.execute("""
    SELECT COUNT(*) AS upcoming_count 
    FROM events 
    WHERE event_date >= CURDATE()
""")
    upcoming_events_count = cursor.fetchone()["upcoming_count"]  
    # Upcoming events list
    cursor.execute("""
    SELECT e.event_id, e.title, e.event_date, e.location,
           (SELECT COUNT(*) FROM registrations r 
            WHERE r.event_id = e.event_id AND r.participant_id = %s) > 0 AS registered
    FROM events e
    WHERE e.event_date >= %s
    ORDER BY e.event_date ASC
    LIMIT 5
""", (user_id, today))
    upcoming_events = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template("dashboard.html",
                           user=user,   # ✅ Pass user here
                           registered_events_count=registered_events_count,
                           attended_events_count=attended_events_count,
                           attendance_percentage=attendance_percentage,
                           upcoming_events_count=upcoming_events_count,
                           upcoming_events=upcoming_events)

# ------------------------
# List all events
# ------------------------
@participant_bp.route("/events")
def events():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # get logged-in user details
    user_id = session.get("user_id")
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    # fetch events
    cursor.execute("SELECT * FROM events ORDER BY event_date ASC")
    events = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("events.html", events=events, user=user,today=today)


@participant_bp.route("/event/<int:event_id>/attendance", methods=["GET", "POST"])
def mark_attendance(event_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get registered participants
    cursor.execute("""
        SELECT r.registration_id, u.name, r.attended
        FROM registrations r
        JOIN users u ON r.user_id = u.user_id
        WHERE r.event_id=%s
    """, (event_id,))
    participants = cursor.fetchall()

    if request.method == "POST":
        attended_ids = request.form.getlist("attended")  # list of registration_ids
        cursor.execute("UPDATE registrations SET attended=FALSE WHERE event_id=%s", (event_id,))
        if attended_ids:
            cursor.executemany("UPDATE registrations SET attended=TRUE WHERE registration_id=%s",
                               [(rid,) for rid in attended_ids])
        conn.commit()
        flash("Attendance marked successfully.", "success")
        return redirect(url_for("organizer.mark_attendance", event_id=event_id))

    return render_template("attendance.html", participants=participants, event_id=event_id)

# ------------------------
# Register for event
# ------------------------
@participant_bp.route("/events/register/<int:event_id>")
def register_event(event_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    user_id = session.get("user_id")

    # Prevent duplicate registration
    cursor.execute("""
        SELECT reg_id FROM registrations 
        WHERE participant_id=%s AND event_id=%s
    """, (user_id, event_id))
    existing = cursor.fetchone()

    if not existing:
        cursor.execute("""
            INSERT INTO registrations (event_id, participant_id, status) 
            VALUES (%s, %s, 'registered')
        """, (event_id, user_id))
        conn.commit()
        flash("You have successfully registered for the event.", "success")
    else:
        flash("You are already registered for this event.", "warning")

    cursor.close()
    conn.close()
    return redirect(url_for("participant.dashboard"))

from datetime import date

@participant_bp.route("/registrations")
def registrations():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get("user_id")

    # Fetch user
    cursor.execute("SELECT user_id, name, email, profile_picture FROM users WHERE user_id=%s", (user_id,))
    user = cursor.fetchone()

    # Fetch registrations with event date
    cursor.execute("""
        SELECT r.reg_id, e.title, e.event_date, r.status AS reg_status
        FROM registrations r
        JOIN events e ON r.event_id = e.event_id
        WHERE r.participant_id=%s
        ORDER BY e.event_date DESC
    """, (user_id,))
    registrations = cursor.fetchall()

    # Update status dynamically based on event date
    today = date.today()
    for reg in registrations:
        if reg['reg_status'] == 'Cancelled':
            reg['status'] = 'Cancelled'
        elif reg['event_date'] < today:
            reg['status'] = 'Completed'
        else:
            reg['status'] = 'Registered'

    cursor.close()
    conn.close()
    return render_template("registrations.html", registrations=registrations, user=user)


@participant_bp.route("/profile")
def profile():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get("user_id")

    cursor.execute("""
        SELECT name, email, phone
        FROM users WHERE user_id=%s
    """, (user_id,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()
    return render_template("profile.html", user=user)

@participant_bp.route("/edit_profile", methods=["GET", "POST"])
def edit_profile():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    user_id = session.get("user_id")

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        

        cursor.execute("""
            UPDATE users
            SET name=%s, email=%s, phone=%s
            WHERE user_id=%s
        """, (name, email, phone, user_id))
        conn.commit()

        cursor.close()
        conn.close()
        flash("✅ Profile updated successfully!", "success")
        return redirect(url_for("participant.profile"))

    # Pre-fill form with existing user details
    cursor.execute("""
        SELECT name, email, phone
        FROM users WHERE user_id=%s
    """, (user_id,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()
    return render_template("participant_edit_profile.html", user=user)
