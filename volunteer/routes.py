from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import mysql.connector
import os
from werkzeug.utils import secure_filename
from models.db import get_db_connection
import functools
volunteer_bp = Blueprint(
    "volunteer", __name__, 
    template_folder="templates"
)

def volunteer_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            flash("You must be logged in to access this page.", "danger")
            return redirect(url_for("volunteer.volunteer_login"))
        if not session.get("is_volunteer"):
            flash("You do not have permission to access this page.", "danger")
            return redirect(url_for("main.home"))  # or wherever you want to send non-volunteers
        return f(*args, **kwargs)
    return decorated_function

@volunteer_bp.route('/dashboard')
@volunteer_required
def dashboard():
    if 'user_id' not in session or session.get('role') != 'volunteer':
        return redirect(url_for('volunteer.login'))
    
    user_id = session['user_id']
    
    # Connect to database
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # =========================
    # Volunteer Stats
    # =========================
    cursor.execute("""
        SELECT 
            (SELECT COUNT(*) FROM volunteer_tasks 
             WHERE volunteer_id = %s AND status = 'assigned') AS upcoming_tasks,
            (SELECT COALESCE(SUM(hours_contributed), 0) FROM volunteer_tasks 
             WHERE volunteer_id = %s AND status = 'completed') AS total_hours,
            (SELECT COUNT(DISTINCT event_id) FROM volunteer_tasks 
             WHERE volunteer_id = %s AND status = 'completed') AS events_participated,
            (SELECT COALESCE(SUM(hours_contributed), 0) FROM volunteer_tasks 
             WHERE volunteer_id = %s AND status = 'completed' AND DATE(created_at) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)) AS weekly_hours,
            (SELECT COALESCE(SUM(hours_contributed), 0) FROM volunteer_tasks 
             WHERE volunteer_id = %s AND status = 'completed' AND MONTH(created_at) = MONTH(CURDATE())) AS monthly_hours
    """, (user_id, user_id, user_id, user_id, user_id))
    stats = cursor.fetchone()
    
    # Completion rate and task stats for the chart
    cursor.execute("""
        SELECT 
            COUNT(*) AS total_tasks,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed_tasks
        FROM volunteer_tasks 
        WHERE volunteer_id = %s
    """, (user_id,))
    
    task_stats = cursor.fetchone()
    stats['completion_rate'] = round(
        (task_stats['completed_tasks'] / task_stats['total_tasks'] * 100), 2
    ) if task_stats['total_tasks'] > 0 else 0
    
    # =========================
    # Upcoming Tasks (assigned + event not completed)
    # =========================
    cursor.execute("""
        SELECT vt.task_id, vt.task_description, vt.status, vt.hours_contributed,
               e.event_id, e.title AS event_title, e.event_date
        FROM volunteer_tasks vt
        JOIN events e ON vt.event_id = e.event_id
        WHERE vt.volunteer_id = %s 
          AND vt.status = 'assigned'
          AND e.status IN ('upcoming', 'ongoing')
        ORDER BY e.event_date ASC
        LIMIT 5
    """, (user_id,))
    
    upcoming_tasks = cursor.fetchall()
    
    # =========================
    # Upcoming Events
    # =========================
    cursor.execute("""
        SELECT e.*, 
               (SELECT COUNT(*) FROM volunteer_tasks 
                WHERE event_id = e.event_id) AS volunteers_registered
        FROM events e
        WHERE e.event_date >= CURDATE() 
          AND e.status = 'upcoming'
        ORDER BY e.event_date ASC
        LIMIT 3
    """)
    
    upcoming_events = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'volunteer_dashboard.html', 
        stats=stats,
        task_stats=task_stats,  # Pass task_stats for the chart
        upcoming_tasks=upcoming_tasks,
        upcoming_events=upcoming_events
    )

# Volunteer Signup - FIXED
@volunteer_bp.route('/signup', methods=['GET', 'POST'])
@volunteer_required
def signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        phone = request.form.get('phone')
        skills = request.form.getlist('skills')
        # bio = request.form.get('bio')
        
        # Validate inputs
        if not all([name, email, password, confirm_password]):
            flash('Please fill all required fields', 'danger')
            return render_template('volunteer_signup.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'danger')
            return render_template('volunteer_signup.html')
        
        # Check if user already exists
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            flash('Email already registered', 'danger')
            cursor.close()
            conn.close()
            return render_template('volunteer_signup.html')
        
        # Get volunteer role ID
        cursor.execute("SELECT role_id FROM roles WHERE role_name = 'volunteer'")
        role = cursor.fetchone()
        
        if not role:
            flash('System error: Volunteer role not found', 'danger')
            cursor.close()
            conn.close()
            return render_template('volunteer_signup.html')
        
        # Create new user with volunteer-specific fields
        hashed_password = generate_password_hash(password)
        skills_str = ','.join(skills) if skills else None
        
        cursor.execute("""
            INSERT INTO users (name, email, password_hash, role_id, phone,skills, is_volunteer)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (name, email, hashed_password, role['role_id'], phone,skills_str, True))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('volunteer.login'))
    
    return render_template('volunteer_signup.html')

# Volunteer Login - UPDATED with is_volunteer check
@volunteer_bp.route('/login', methods=['GET', 'POST'])
@volunteer_required
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        remember = request.form.get('remember')
        
        if not all([email, password]):
            flash('Please enter both email and password', 'danger')
            return render_template('login.html')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT u.*, r.role_name 
            FROM users u 
            JOIN roles r ON u.role_id = r.role_id 
            WHERE u.email = %s AND r.role_name = 'volunteer' AND u.is_volunteer = TRUE
        """, (email,))
        
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['name'] = user['name']
            session['email'] = user['email']
            session['role'] = user['role_name']
            
            if remember:
                session.permanent = True
            
            flash('Login successful!', 'success')
            return redirect(url_for('volunteer.dashboard'))
        else:
            flash('Invalid email or password, or account is not registered as a volunteer', 'danger')
            return render_template('volunteer_login.html')
    
    return render_template('volunteer_login.html')

# Available Events
# Available Events with Pagination
@volunteer_bp.route('/events')
@volunteer_required
def events():
    if 'user_id' not in session or session.get('role') != 'volunteer':
        return redirect(url_for('volunteer.login'))

    user_id = session['user_id']

    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 6  # number of events per page
    offset = (page - 1) * per_page

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Count total upcoming events
    cursor.execute("""
        SELECT COUNT(*) as total_events
        FROM events
        WHERE event_date >= CURDATE() AND status = 'upcoming'
    """)
    total_events = cursor.fetchone()['total_events']

    # Fetch events for current page
    cursor.execute("""
        SELECT e.*, 
               (SELECT COUNT(*) FROM volunteer_tasks 
                WHERE event_id = e.event_id) as volunteers_registered,
               EXISTS(SELECT 1 FROM volunteer_tasks 
                      WHERE event_id = e.event_id AND volunteer_id = %s) as is_registered
        FROM events e
        WHERE e.event_date >= CURDATE() AND e.status = 'upcoming'
        ORDER BY e.event_date ASC
        LIMIT %s OFFSET %s
    """, (user_id, per_page, offset))

    events = cursor.fetchall()
    cursor.close()
    conn.close()

    # Calculate total pages
    total_pages = (total_events + per_page - 1) // per_page

    return render_template(
        'volunteer_events.html',
        events=events,
        page=page,
        total_pages=total_pages
    )

# Mark Task as Complete
@volunteer_bp.route('/tasks/<int:task_id>/complete', methods=['POST'])
@volunteer_required
def complete_task(task_id):
    if 'user_id' not in session or session.get('role') != 'volunteer':
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Verify the task belongs to the volunteer and get hours
    cursor.execute("""
        SELECT * FROM volunteer_tasks 
        WHERE task_id = %s AND volunteer_id = %s
    """, (task_id, user_id))
    
    task = cursor.fetchone()
    
    if not task:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'Task not found'}), 404
    
    # Update task status to completed
    cursor.execute("""
        UPDATE volunteer_tasks 
        SET status = 'completed', updated_at = NOW() 
        WHERE task_id = %s
    """, (task_id,))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Task marked as completed'})

# Volunteer Tasks Page
@volunteer_bp.route('/tasks')
@volunteer_required
def tasks():
    if 'user_id' not in session or session.get('role') != 'volunteer':
        return redirect(url_for('volunteer.login'))
    
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Get all tasks for the volunteer with event details
    cursor.execute("""
        SELECT vt.*, e.title as event_title, e.event_date, e.event_time, e.location,
               e.image_url as event_image
        FROM volunteer_tasks vt
        JOIN events e ON vt.event_id = e.event_id
        WHERE vt.volunteer_id = %s
        ORDER BY e.event_date ASC, vt.status
    """, (user_id,))
    
    tasks = cursor.fetchall()
    
    # Separate tasks by status for better organization
    assigned_tasks = [task for task in tasks if task['status'] == 'assigned']
    completed_tasks = [task for task in tasks if task['status'] == 'completed']
    
    cursor.close()
    conn.close()
    
    return render_template('tasks.html', 
                         assigned_tasks=assigned_tasks,
                         completed_tasks=completed_tasks)


# Volunteer Profile
import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = "static/uploads/profile_pictures"

@volunteer_bp.route("/profile", methods=["GET", "POST"])
@volunteer_required
def volunteer_profile():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        skills = request.form.getlist("skills")

        profile_picture = None
        if "profile_picture" in request.files:
            file = request.files["profile_picture"]
            if file and file.filename:
                filename = secure_filename(file.filename)

                # Absolute path from this file → static/uploads/profile_pictures
                base_dir = os.path.dirname(os.path.dirname(__file__))  # go up one level from /volunteer
                upload_folder = os.path.join(base_dir, "static", "uploads", "profile_pictures")
                os.makedirs(upload_folder, exist_ok=True)

                filepath = os.path.join(upload_folder, filename)
                file.save(filepath)

                profile_picture = f"uploads/profile_pictures/{filename}"

        # Update DB
        if profile_picture:
            cursor.execute("""
                UPDATE users 
                SET name = %s, phone = %s, skills = %s, profile_picture = %s
                WHERE user_id = %s
            """, (name, phone, ",".join(skills), profile_picture, session["user_id"]))
        else:
            cursor.execute("""
                UPDATE users 
                SET name = %s, phone = %s, skills = %s
                WHERE user_id = %s
            """, (name, phone, ",".join(skills), session["user_id"]))

        conn.commit()

    # Fetch updated user
    cursor.execute("SELECT * FROM users WHERE user_id = %s", (session["user_id"],))
    user = cursor.fetchone()

    # ✅ Convert skills string into a list
    if user and user.get("skills"):
        user["skills_list"] = user["skills"].split(",")
    else:
        user["skills_list"] = []

    cursor.close()
    conn.close()

    return render_template("volunteer_profile.html", user=user)



@volunteer_bp.route("/events/<int:event_id>")
@volunteer_required
def event_detail(event_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch the event with organizer information
    cursor.execute("""
        SELECT 
            e.*, 
            u.name as organizer_name,
            (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.event_id) as volunteers_registered
        FROM events e 
        JOIN users u ON e.organizer_id = u.user_id 
        WHERE e.event_id = %s
    """, (event_id,))
    event = cursor.fetchone()

    cursor.close()
    conn.close()

    if not event:
        return "Event not found", 404

    # Rename keys to match template expectations
    event['date'] = event.get('event_date')
    event['volunteers_needed'] = event.get('volunteer_required')
    event['image'] = event.get('image_url')
    
    # Format the date if it's a string
    if event['date'] and isinstance(event['date'], str):
        try:
            event['date'] = datetime.strptime(event['date'], '%Y-%m-%d').date()
        except ValueError:
            # Handle different date formats if needed
            pass

    return render_template("volunteer_event_detail.html", event=event)

@volunteer_bp.route('/history')
@volunteer_required
def history():
    user_id = session['user_id']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Fetch completed tasks with event info
    cursor.execute("""
        SELECT e.title AS event_name, e.event_date, e.location, vt.status
        FROM volunteer_tasks vt
        JOIN events e ON vt.event_id = e.event_id
        WHERE vt.volunteer_id = %s AND vt.status = 'completed'
        ORDER BY e.event_date DESC
    """, (user_id,))
    
    history_records = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template("volunteer_history.html", history=history_records)
