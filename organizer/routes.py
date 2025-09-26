# organizer/routes.py - Updated with complete functionality

from flask import (
    Blueprint, render_template, session, flash, redirect,
    url_for, request, current_app, jsonify
)
from models.db import get_db_connection
from datetime import date, datetime
import functools
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

organizer_bp = Blueprint("organizer", __name__, template_folder="templates")

# -------------------------
# Helper to create notifications
# -------------------------
def create_notification(user_id, message, event_id=None):
    conn, cursor = get_db_connection(), None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notifications (user_id, event_id, message, is_read, created_at) VALUES (%s, %s, %s, FALSE, NOW())",
            (user_id, event_id, message)
        )
        conn.commit()
    except Exception as e:
        print(f"DEBUG: Failed to create notification: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()



# -------------------------
# Organizer authentication decorator
# -------------------------
def organizer_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('user_id') or session.get('role') != 'organizer':
            flash("Access denied. Organizer privileges required.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


# -------------------------
# File Upload Helpers
# -------------------------
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# -------------------------
# Organizer Dashboard
# -------------------------
@organizer_bp.route("/dashboard")
@organizer_required
def dashboard():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session.get('user_id')

        # Get organizer stats
        cursor.execute(
            "SELECT COUNT(*) as total_events FROM events WHERE organizer_id=%s",
            (user_id,)
        )
        total_events = cursor.fetchone()['total_events']

        today = date.today()
        cursor.execute(
            "SELECT COUNT(*) as upcoming_events FROM events WHERE organizer_id=%s AND event_date >= %s",
            (user_id, today)
        )
        upcoming_events = cursor.fetchone()['upcoming_events']

        cursor.execute("""
            SELECT COUNT(DISTINCT r.participant_id) as total_participants 
            FROM registrations r 
            JOIN events e ON r.event_id = e.event_id 
            WHERE e.organizer_id=%s
        """, (user_id,))
        total_participants = cursor.fetchone()['total_participants']

        # Get active volunteers count
        cursor.execute("""
            SELECT COUNT(*) as active_volunteers 
            FROM users 
            WHERE is_volunteer = TRUE AND status='active'
        """)
        active_volunteers = cursor.fetchone()['active_volunteers']

        # Get recent events
        cursor.execute("""
            SELECT e.event_id, e.title, e.event_date, e.event_time, e.location, 
                   e.total_tickets,
                   COUNT(r.reg_id) as registrations_count
            FROM events e 
            LEFT JOIN registrations r ON e.event_id = r.event_id
            WHERE e.organizer_id = %s
            GROUP BY e.event_id, e.title, e.event_date, e.event_time, e.location, e.total_tickets
            ORDER BY e.event_date DESC
            LIMIT 5
        """, (user_id,))
        recent_events = cursor.fetchall()

        # Get recent participants
        cursor.execute("""
            SELECT u.name, u.email, e.title as event_name, r.registered_at
            FROM registrations r
            JOIN users u ON r.participant_id = u.user_id
            JOIN events e ON r.event_id = e.event_id
            WHERE e.organizer_id = %s
            ORDER BY r.registered_at DESC
            LIMIT 5
        """, (user_id,))
        recent_participants = cursor.fetchall()

        # Get assigned tasks with volunteer and event details
        # In your dashboard route, replace the assigned_tasks query with this:
        cursor.execute("""
    SELECT vt.task_id AS id,
           vt.task_description AS description,
           vt.created_at,
           vt.status,
           u.name AS volunteer_name,
           e.title AS event_name,
           vt.hours_contributed
    FROM volunteer_tasks vt
    LEFT JOIN users u ON vt.volunteer_id = u.user_id
    LEFT JOIN events e ON vt.event_id = e.event_id
    WHERE e.organizer_id = %s
    ORDER BY vt.created_at DESC
""", (user_id,))


        assigned_tasks = cursor.fetchall()

        # Get volunteers for task assignment dropdown
        cursor.execute("""
            SELECT user_id as id, name, email 
            FROM users 
            WHERE is_volunteer = TRUE AND status = 'active'
            ORDER BY name
        """)
        volunteers = cursor.fetchall()

        # Get events for task assignment dropdown
        cursor.execute("""
            SELECT event_id, title, event_date 
            FROM events 
            WHERE organizer_id = %s AND event_date >= CURDATE()
            ORDER BY event_date
        """, (user_id,))
        events = cursor.fetchall()

        # Get current user details
        cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        user = cursor.fetchone()

        stats = {
            'total_events': total_events,
            'upcoming_events': upcoming_events,
            'total_participants': total_participants,
            'active_volunteers': active_volunteers
        }
       # In your dashboard route, replace the chart data queries with these:

# Events per Month (Improved to include year)
        cursor.execute("""
            SELECT DATE_FORMAT(event_date, '%Y-%m') as month, COUNT(*) as total
            FROM events
            WHERE organizer_id = %s
            GROUP BY month
            ORDER BY month
        """, (user_id,))
        events_per_month_data = cursor.fetchall()

        # Participant Registrations Trend (Corrected GROUP BY)
        cursor.execute("""
            SELECT DATE(registered_at) as reg_date, COUNT(*) as total
            FROM registrations r
            JOIN events e ON r.event_id = e.event_id
            WHERE e.organizer_id = %s
            GROUP BY DATE(registered_at)
            ORDER BY DATE(registered_at)
        """, (user_id,))
        participants_trend_data = cursor.fetchall()
        # The rest of the function remains the same...
        return render_template(
            "organizer_dashboard.html",
            stats=stats,
            user=user,
            recent_events=recent_events,
            recent_participants=recent_participants,
            assigned_tasks=assigned_tasks,
            volunteers=volunteers,
            events=events,
            events_per_month=events_per_month_data, # Pass the corrected data
            participants_trend=participants_trend_data # Pass the corrected data
        )

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        stats = {
            'total_events': 0,
            'upcoming_events': 0,
            'total_participants': 0,
            'active_volunteers': 0
        }
        return render_template(
            "organizer_dashboard.html",
            stats=stats,
            user={},
            recent_events=[],
            recent_participants=[],
            assigned_tasks=[],
            volunteers=[],
            events=[]
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# In organizer/routes.py

@organizer_bp.route("/assign_task", methods=["POST"])
@organizer_required
def assign_task():
    # Debug: Check if user is authenticated
    if not session.get('user_id') or session.get('role') != 'organizer':
        print("DEBUG: User not authenticated or not organizer")
        print(f"DEBUG: user_id: {session.get('user_id')}, role: {session.get('role')}")
        flash("Session expired. Please log in again.", "danger")
        return redirect(url_for('auth.login'))
    
    description = request.form.get("description")
    volunteer_id = request.form.get("volunteer_id")
    event_id = request.form.get("event_id") or None  # Handle empty string
    hours_contributed = request.form.get("hours_contributed")
    print(f"DEBUG: Received task assignment - desc: {description}, volunteer: {volunteer_id}, event: {event_id}, hours: {hours_contributed}")

    if not description or not volunteer_id or not hours_contributed:
        flash("Task description, volunteer, and hours contribution are required.", "danger")
        return redirect(url_for("organizer.dashboard"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        user_id = session.get('user_id')
        print(f"DEBUG: Current user ID: {user_id}")
        
        # Validate that the event belongs to the organizer if provided
        if event_id:
            cursor.execute("""
                SELECT * FROM events 
                WHERE event_id = %s AND organizer_id = %s
            """, (event_id, user_id))
            event = cursor.fetchone()
            if not event:
                flash("Invalid event selection.", "danger")
                return redirect(url_for("organizer.dashboard"))

        cursor.execute("""
            INSERT INTO volunteer_tasks (task_description, volunteer_id, event_id,hours_contributed, status)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            description,
            volunteer_id,
            event_id,  # This can be None if no event selected
            hours_contributed,
            "assigned"  # default status
        ))
         
        conn.commit()
        flash("Task assigned successfully!", "success")
        print("DEBUG: Task assigned successfully")
        
    except Exception as e:
        print(f"DEBUG: Error assigning task: {e}")
        flash("Error assigning task.", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for("organizer.dashboard"))

# -------------------------
# Organizer Profile
# -------------------------
@organizer_bp.route("/profile", methods=["GET", "POST"])
@organizer_required
def profile():
    user_id = session.get("user_id")

    if request.method == "POST":
        # Get form values first
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form.get("phone")
        organization = request.form.get("organization")
        bio = request.form.get("bio")

        # Handle profile picture upload
        profile_picture = None
        if "profile_picture" in request.files:
            file = request.files["profile_picture"]
            if file and file.filename:
                filename = secure_filename(file.filename)
                # Create upload directory if it doesn't exist
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'profiles')
                os.makedirs(upload_folder, exist_ok=True)
                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)
                profile_picture = f"/static/uploads/profiles/{filename}"  # Save as relative path for template

        # Update DB
        conn = get_db_connection()
        cursor = conn.cursor()
        if profile_picture:
            cursor.execute("""
                UPDATE users
                SET name = %s, email = %s, phone = %s, organization = %s, bio = %s,
                    profile_picture = %s
                WHERE user_id = %s
            """, (name, email, phone, organization, bio, profile_picture, user_id))
        else:
            cursor.execute("""
                UPDATE users
                SET name = %s, email = %s, phone = %s, organization = %s, bio = %s
                WHERE user_id = %s
            """, (name, email, phone, organization, bio, user_id))
        conn.commit()
        cursor.close()
        conn.close()

        flash("Profile updated successfully!", "success")
        return redirect(url_for("organizer.profile"))

    # If GET request → fetch user details
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) AS total_events FROM events WHERE organizer_id = %s", (user_id,))
    stats = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template("organizer_profile.html", user=user, stats=stats)


# -------------------------
# All Events
# -------------------------
@organizer_bp.route("/events")
@organizer_required
def all_events():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session.get('user_id')

        # Get filter parameters
        status_filter = request.args.get('status', 'all')
        search_query = request.args.get('q', '')

        # Build query with participant count
        query = """
            SELECT e.event_id, e.title, e.description, e.location, e.event_date, e.event_time,
                   e.category, e.total_tickets, e.image_url,
                   COUNT(r.reg_id) AS participant_count
            FROM events e
            LEFT JOIN registrations r ON e.event_id = r.event_id
            WHERE e.organizer_id = %s
        """
        params = [user_id]

        if search_query:
            query += " AND (e.title LIKE %s OR e.description LIKE %s OR e.location LIKE %s)"
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])

        if status_filter == 'upcoming':
            query += " AND e.event_date >= CURDATE()"
        elif status_filter == 'past':
            query += " AND e.event_date < CURDATE()"

        query += " GROUP BY e.event_id ORDER BY e.event_date DESC"

        cursor.execute(query, params)
        events = cursor.fetchall()

        cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        user = cursor.fetchone()

        return render_template("organizer_events.html",
                               events=events,
                               user=user,
                               status_filter=status_filter,
                               search_query=search_query,
                               current_date=date.today())
    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return render_template("organizer_events.html",
                               events=[],
                               user={},
                               status_filter='all',
                               search_query='',
                               current_date=date.today())
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# -------------------------
# Create Event - GET
# -------------------------
@organizer_bp.route("/create_event")
@organizer_required
def create_event():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        user_id = session.get('user_id')

        cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        user = cursor.fetchone()

        return render_template("organizer_create_event.html", user=user)
    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return render_template("organizer_create_event.html", user={})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# -------------------------
# Create Event - POST
# -------------------------
@organizer_bp.route("/create_event", methods=['POST'])
@organizer_required
def create_event_post():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session.get('user_id')

        title = request.form.get('title')
        description = request.form.get('description')
        event_date = request.form.get('event_date')
        event_time = request.form.get('event_time')
        location = request.form.get('location')
        category = request.form.get('category')
        total_tickets = request.form.get('total_tickets')
        

        # Handle file upload
        image_url = None
        if 'event_image' in request.files:
            file = request.files['event_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads','events')
                os.makedirs(upload_folder, exist_ok=True)
                file_path = os.path.join(upload_folder, unique_filename)
                file.save(file_path)
                image_url = f"/static/uploads/events/{unique_filename}"

        cursor.execute("""
            INSERT INTO events (organizer_id, title, description, event_date, event_time, location, category, total_tickets,  image_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, title, description, event_date, event_time, location, category, total_tickets, image_url))
        event_id = cursor.lastrowid  # get new event ID
        conn.commit()
        # Create notification
        create_notification(user_id, f"You have successfully created the event: {title}", event_id)
        flash("Event created successfully!", "success")
        return redirect(url_for('organizer.all_events'))

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('organizer.create_event'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# -------------------------
# Edit Event - GET
# -------------------------
@organizer_bp.route("/edit_event/<int:event_id>")
@organizer_required
def edit_event(event_id):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session.get('user_id')

        cursor.execute("SELECT * FROM events WHERE event_id=%s AND organizer_id=%s", (event_id, user_id))
        event = cursor.fetchone()

        if not event:
            flash("Event not found or you don't have permission to edit it.", "danger")
            return redirect(url_for('organizer.all_events'))

        cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        user = cursor.fetchone()

        return render_template("organizer_edit_event.html", event=event, user=user)

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('organizer.all_events'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# -------------------------
# Edit Event - POST
# -------------------------
@organizer_bp.route("/edit_event/<int:event_id>", methods=['POST'])
@organizer_required
def edit_event_post(event_id):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session.get('user_id')

        cursor.execute("SELECT * FROM events WHERE event_id=%s AND organizer_id=%s", (event_id, user_id))
        event = cursor.fetchone()

        if not event:
            flash("Event not found or you don't have permission to edit it.", "danger")
            return redirect(url_for('organizer.all_events'))

        title = request.form.get('title')
        description = request.form.get('description')
        event_date = request.form.get('event_date')
        event_time = request.form.get('event_time')
        location = request.form.get('location')
        category = request.form.get('category')
        total_tickets = request.form.get('total_tickets')
        

        image_url = event['image_url']
        if 'event_image' in request.files:
            file = request.files['event_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'events')
                os.makedirs(upload_folder, exist_ok=True)
                file_path = os.path.join(upload_folder, unique_filename)
                file.save(file_path)
                image_url = f"/static/uploads/events/{unique_filename}"

        cursor.execute("""
            UPDATE events 
            SET title=%s, description=%s, event_date=%s, event_time=%s, location=%s, category=%s, total_tickets=%s,  image_url=%s
            WHERE event_id=%s
        """, (title, description, event_date, event_time, location, category, total_tickets,  image_url, event_id))

        conn.commit()
        # Create notification
        create_notification(user_id, f"You have updated the event: {title}", event_id)
        flash("Event updated successfully!", "success")
        return redirect(url_for('organizer.all_events'))

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('organizer.edit_event', event_id=event_id))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# -------------------------
# Delete Event
# -------------------------
@organizer_bp.route("/delete_event/<int:event_id>", methods=['POST'])
@organizer_required
def delete_event(event_id):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session.get('user_id')

        # Check if the event belongs to the organizer
        cursor.execute("SELECT * FROM events WHERE event_id=%s AND organizer_id=%s", (event_id, user_id))
        event = cursor.fetchone()

        if not event:
            flash("Event not found or you don't have permission to delete it.", "danger")
            return redirect(url_for('organizer.all_events'))

        # First delete related notifications
        cursor.execute("DELETE FROM notifications WHERE event_id=%s", (event_id,))

        # Now delete the event
        cursor.execute("DELETE FROM events WHERE event_id=%s", (event_id,))
        conn.commit()

        flash("Event deleted successfully!", "success")
        return redirect(url_for('organizer.all_events'))

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('organizer.all_events'))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# -------------------------
# Task Management Routes
# -------------------------

# @organizer_bp.route('/assign_task', methods=['POST'])
# def assign_task_post():
#     if 'user_id' not in session or session.get('role') != 'organizer':
#         return redirect(url_for('auth.login'))

#     event_id = request.form.get('event_id')
#     volunteer_id = request.form.get('volunteer_id')
#     event_id = request.form.get("event_id")
#     task_description = request.form.get('task_description')

#     if not event_id or not volunteer_id or not task_description:
#         flash("All fields are required!", "danger")
#         return redirect(url_for('organizer.dashboard'))

#     conn = get_db_connection()
#     cursor = conn.cursor()

#     cursor.execute("""
#         INSERT INTO volunteer_tasks (event_id, volunteer_id, task_description, status)
#         VALUES (%s, %s, %s, 'assigned')
#     """, (event_id, volunteer_id, task_description))

#     conn.commit()
#     cursor.close()
#     conn.close()

#     flash("Task assigned successfully!", "success")
#     return redirect(url_for('organizer.dashboard'))



@organizer_bp.route("/edit_task/<int:task_id>", methods=["POST"])
@organizer_required
def edit_task(task_id):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        user_id = session.get('user_id')
        description = request.form.get('description')
        volunteer_id = request.form.get('volunteer_id')
        event_id = request.form.get('event_id') or None
        status = request.form.get('status', 'assigned')
        
        # Verify task belongs to organizer's event
        cursor.execute("""
            SELECT vt.* FROM volunteer_tasks vt
            JOIN events e ON vt.event_id = e.event_id
            WHERE vt.task_id = %s AND e.organizer_id = %s
        """, (task_id, user_id))
        
        task = cursor.fetchone()
        if not task:
            flash("Task not found or you don't have permission to edit it.", "danger")
            return redirect(url_for('organizer.dashboard'))
        
        # Validate volunteer exists and is a volunteer
        cursor.execute("""
            SELECT * FROM users 
            WHERE user_id = %s AND is_volunteer = TRUE
        """, (volunteer_id,))
        
        volunteer = cursor.fetchone()
        if not volunteer:
            flash("Invalid volunteer selection.", "danger")
            return redirect(url_for('organizer.dashboard'))
        
        # Validate event belongs to organizer if provided
        if event_id:
            cursor.execute("""
                SELECT * FROM events 
                WHERE event_id = %s AND organizer_id = %s
            """, (event_id, user_id))
            
            event = cursor.fetchone()
            if not event:
                flash("Invalid event selection.", "danger")
                return redirect(url_for('organizer.dashboard'))
        
        # Update task
        cursor.execute("""
            UPDATE volunteer_tasks 
            SET volunteer_id = %s, event_id = %s, task_description = %s, 
                status = %s
            WHERE task_id = %s
        """, (volunteer_id, event_id, description, status, task_id))
        
        conn.commit()
        flash("Task updated successfully!", "success")
        
    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    
    return redirect(url_for('organizer.dashboard'))


@organizer_bp.route("/delete_task/<int:task_id>", methods=["POST"])
@organizer_required
def delete_task(task_id):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        user_id = session.get('user_id')
        
        # Verify task belongs to organizer's event
        cursor.execute("""
            SELECT vt.* FROM volunteer_tasks vt
            JOIN events e ON vt.event_id = e.event_id
            WHERE vt.task_id = %s AND e.organizer_id = %s
        """, (task_id, user_id))
        
        task = cursor.fetchone()
        if not task:
            flash("Task not found or you don't have permission to delete it.", "danger")
            return redirect(url_for('organizer.dashboard'))
        
        # Delete task
        cursor.execute("DELETE FROM volunteer_tasks WHERE task_id = %s", (task_id,))
        conn.commit()
        
        flash("Task deleted successfully!", "success")
        
    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
    
    return redirect(url_for('organizer.dashboard'))


@organizer_bp.route("/get_task/<int:task_id>")
@organizer_required
def get_task(task_id):
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        user_id = session.get('user_id')
        
        # Get task with volunteer and event details
        cursor.execute("""
            SELECT vt.*, u.name as volunteer_name, u.email as volunteer_email,
                   e.title as event_title
            FROM volunteer_tasks vt
            LEFT JOIN users u ON vt.volunteer_id = u.user_id
            LEFT JOIN events e ON vt.event_id = e.event_id
            WHERE vt.task_id = %s AND e.organizer_id = %s
        """, (task_id, user_id))
        
        task = cursor.fetchone()
        
        if not task:
            return jsonify({"error": "Task not found"}), 404
        
        # Format for JSON response
        task_data = {
            "id": task["task_id"],
            "description": task["task_description"],
            "volunteer_id": task["volunteer_id"],
            "event_id": task["event_id"],
            "status": task["status"]
        }
        
        return jsonify(task_data)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# -------------------------
# Notifications
# -------------------------
@organizer_bp.route('/notifications')
@organizer_required
def notifications_page():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        user_id = session.get('user_id')

        cursor.execute("""
            SELECT * FROM notifications 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        """, (user_id,))
        notifications = cursor.fetchall()

        cursor.execute("""
            UPDATE notifications 
            SET is_read = TRUE 
            WHERE user_id = %s AND is_read = FALSE
        """, (user_id,))
        conn.commit()

        cursor.execute("SELECT * FROM users WHERE user_id=%s", (user_id,))
        user = cursor.fetchone()

        return render_template("notifications.html",
                               notifications=notifications,
                               user=user)

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return render_template("notifications.html",
                               notifications=[],
                               user={})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@organizer_bp.route('/mark_notification_read', methods=['POST'])
@organizer_required
def mark_notification_read():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        notification_id = request.json.get('notification_id')
        user_id = session.get('user_id')

        cursor.execute("""
            UPDATE notifications 
            SET is_read = TRUE 
            WHERE notif_id = %s AND user_id = %s
        """, (notification_id, user_id))
        conn.commit()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@organizer_bp.route('/mark_all_notifications_read', methods=['POST'])
@organizer_required
def mark_all_notifications_read():
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id')

    # Mark all as read for the current user
    cursor.execute("UPDATE notifications SET is_read = TRUE WHERE user_id = %s", (user_id,))
    conn.commit()

    cursor.close()
    conn.close()
    return jsonify({"success": True})


@organizer_bp.route('/clear_all_notifications', methods=['POST'])
@organizer_required
def clear_all_notifications():
    conn = get_db_connection()
    cursor = conn.cursor()
    user_id = session.get('user_id')

    cursor.execute("DELETE FROM notifications WHERE user_id = %s", (user_id,))
    conn.commit()

    cursor.close()
    conn.close()
    return jsonify({"success": True})


#==================================
# CHANGE PASSWORD
# ==================================
@organizer_bp.route("/change_password", methods=["GET", "POST"])
@organizer_required
def change_password():
    user_id = session.get("user_id")

    if request.method == "POST":
        current_password = request.form["current_password"]
        new_password = request.form["new_password"]
        confirm_password = request.form["confirm_password"]

        # DB connection
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Fetch existing password hash
        cursor.execute("SELECT password_hash FROM users WHERE user_id = %s", (user_id,))
        user_data = cursor.fetchone()

        if not user_data or not check_password_hash(user_data["password_hash"], current_password):
            flash("Current password is incorrect!", "danger")
            return redirect(url_for("organizer.change_password"))

        if new_password != confirm_password:
            flash("New password and confirm password do not match!", "danger")
            return redirect(url_for("organizer.change_password"))

        # Update password
        hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (hashed_password, user_id))
        conn.commit()

        cursor.close()
        conn.close()

        flash("Password changed successfully!", "success")
        return redirect(url_for("organizer.profile"))

    # GET request: fetch user info for navbar
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT name, profile_picture FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template("change_password.html", user=user)


#============================
# VIEW EVENT
#===========================
@organizer_bp.route('/event/view/<int:event_id>')
def view_event(event_id):
    user_id = session.get("user_id")
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # 1️⃣ Fetch event details including image_url
    cursor.execute("""
        SELECT 
            event_id, title, description, event_date, event_time, 
            location, total_tickets, status, image_url
        FROM events
        WHERE event_id = %s
    """, (event_id,))
    event = cursor.fetchone()

    if event is None:
        cursor.close()
        conn.close()
        flash('Event not found!', 'danger')
        return redirect(url_for('organizer.all_events'))

    # Ensure event_date is a date object
    if isinstance(event['event_date'], str):
        from datetime import datetime
        event['event_date'] = datetime.strptime(event['event_date'], '%Y-%m-%d').date()

    # 2️⃣ Get participant count
    cursor.execute("""
        SELECT IFNULL(SUM(ticket_count), 0) AS participant_count
        FROM registrations
        WHERE event_id = %s
    """, (event_id,))
    participant_data = cursor.fetchone()
    event['participant_count'] = participant_data['participant_count']

    # 3️⃣ Ensure status is a string
    if event['status'] is None:
        event['status'] = 'upcoming'
    else:
        event['status'] = str(event['status'])

    # 4️⃣ Fetch user info for navbar
    cursor.execute("SELECT name, profile_picture FROM users WHERE user_id = %s", (user_id,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    from datetime import date
    current_date = date.today()

    return render_template(
        'organizer_view_event.html',
        user=user,
        event=event,
        current_date=current_date
    )

