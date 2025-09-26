from flask import Blueprint, render_template, session, flash, redirect, url_for, request,jsonify
from models.db import get_db_connection
from datetime import date
import functools
from math import ceil
from datetime import date

admin_bp = Blueprint("admin", __name__, template_folder="templates")

# Admin authentication decorator
def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            flash("Access denied. Admin privileges required.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Pagination helper
class Pagination:
    def __init__(self, page, per_page, total_count):
        self.page = page
        self.per_page = per_page
        self.total_count = total_count
    
    @property
    def pages(self):
        return int(ceil(self.total_count / float(self.per_page)))
    
    @property
    def has_prev(self):
        return self.page > 1
    
    @property
    def has_next(self):
        return self.page < self.pages
    
    def iter_pages(self, left_edge=2, left_current=2, right_current=5, right_edge=2):
        last = 0
        for num in range(1, self.pages + 1):
            if num <= left_edge or \
               (num > self.page - left_current - 1 and num < self.page + right_current) or \
               num > self.pages - right_edge:
                if last + 1 != num:
                    yield None
                yield num
                last = num

# ---------------- Dashboard ----------------
# ---------------- Dashboard ----------------
@admin_bp.route("/dashboard")
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Volunteers count
    cursor.execute("SELECT COUNT(*) AS count FROM users u JOIN roles r ON u.role_id = r.role_id WHERE r.role_name = 'volunteer'")
    volunteers_count = cursor.fetchone()["count"]

    # Participants count
    cursor.execute("SELECT COUNT(*) AS count FROM users u JOIN roles r ON u.role_id = r.role_id WHERE r.role_name = 'participant'")
    participants_count = cursor.fetchone()["count"]

    # Total events
    cursor.execute("SELECT COUNT(*) AS count FROM events")
    total_events = cursor.fetchone()["count"]

    # Ongoing events
    cursor.execute("SELECT COUNT(*) AS count FROM events WHERE status = 'ongoing'")
    ongoing_events = cursor.fetchone()["count"]

    # ✅ Pagination for upcoming events
    page = request.args.get("page", 1, type=int)
    per_page = 5
    today = date.today()
    cursor.execute("SELECT COUNT(*) AS count FROM events WHERE event_date >= %s AND status != 'completed'", (today,))
    total_upcoming = cursor.fetchone()["count"]

    pagination = Pagination(page, per_page, total_upcoming)
    today = date.today()
    cursor.execute("""
        SELECT e.event_id, e.title, e.event_date AS date, e.status,
               u.name AS organizer_name,
               (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.event_id) AS participant_count
        FROM events e
        LEFT JOIN users u ON e.organizer_id = u.user_id
        WHERE e.event_date >= %s AND e.status != 'completed'
        ORDER BY e.event_date ASC
        LIMIT %s OFFSET %s
    """, (today, per_page, (page - 1) * per_page))
    upcoming_events = cursor.fetchall()
    

    # 📈 Event attendance per month (line chart)
    cursor.execute("""
    SELECT DATE_FORMAT(r.registered_at, '%Y-%m') AS month, COUNT(*) AS count
    FROM registrations r
    GROUP BY DATE_FORMAT(r.registered_at, '%Y-%m')
    ORDER BY month
    """)
    monthly_attendance = cursor.fetchall()
    attendance_labels = [row["month"] for row in monthly_attendance]
    attendance_data = [row["count"] for row in monthly_attendance]

    # 📊 User roles distribution (bar chart)
    cursor.execute("""
        SELECT r.role_name, COUNT(*) AS count
        FROM users u
        JOIN roles r ON u.role_id = r.role_id
        GROUP BY r.role_name
    """)
    role_stats = cursor.fetchall()
    role_labels = [row["role_name"].capitalize() for row in role_stats]
    role_data = [row["count"] for row in role_stats]

    # 📊 Event status distribution (for doughnut chart) - FIXED
    cursor.execute("""
        SELECT 
            CASE 
                WHEN event_date < CURDATE() THEN 'completed'
                ELSE status 
            END AS event_status,
            COUNT(*) AS count
        FROM events
        GROUP BY 
            CASE 
                WHEN event_date < CURDATE() THEN 'completed'
                ELSE status 
            END
    """)
    event_status_stats = cursor.fetchall()
    event_status_labels = [row["event_status"].capitalize() for row in event_status_stats]
    event_status_data = [row["count"] for row in event_status_stats]

    conn.close()

    return render_template(
        "admin_dashboard.html",
        admin_name=session.get("name", "Admin"),
        volunteers_count=volunteers_count,
        participants_count=participants_count,
        total_events=total_events,
        ongoing_events=ongoing_events,
        upcoming_events=upcoming_events,
        pagination=pagination,
        attendance_labels=attendance_labels,
        attendance_data=attendance_data,
        role_labels=role_labels,
        role_data=role_data,
        event_status_labels=event_status_labels,
        event_status_data=event_status_data
    )


# ---------------- Manage Users ----------------
# ---------------- Manage Users with Role Filtering + Pagination ----------------
@admin_bp.route("/manage_users")
@admin_required
def manage_users():
    role_filter = request.args.get('role', 'all')
    page = request.args.get('page', 1, type=int)  # current page number
    per_page = 5  # ✅ 5 users per page

    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Base query
        query = """
            SELECT u.*, r.role_name 
            FROM users u 
            JOIN roles r ON u.role_id = r.role_id
        """
        params = []

        if role_filter != 'all':
            query += " WHERE LOWER(r.role_name) = LOWER(%s)"
            params.append(role_filter)

        # Count total users for pagination
        count_query = f"SELECT COUNT(*) as total FROM ({query}) as sub"
        cursor.execute(count_query, params)
        total_users = cursor.fetchone()['total']

        # Add ordering + limit/offset
        query += " ORDER BY u.created_at DESC LIMIT %s OFFSET %s"
        params.extend([per_page, (page - 1) * per_page])

        # Debugging
        print("DEBUG: role_filter =", role_filter)
        print("DEBUG: final query =", query, "params =", params)

        cursor.execute(query, params)
        users = cursor.fetchall()
             # 🔑 Ensure is_active is boolean for all users
        for u in users:
           u["is_active"] = (u["status"].lower() == "active")
        total_pages = (total_users + per_page - 1) // per_page  # ceil

        return render_template(
            "admin_manage_users.html",
            users=users,
            current_filter=role_filter,
            page=page,
            total_pages=total_pages
        )

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return render_template(
            "admin_manage_users.html",
            users=[],
            current_filter=role_filter,
            page=1,
            total_pages=1
        )
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
# @admin_bp.route("/delete_user/<int:user_id>", methods=["POST"])
# @admin_required
# def delete_user(user_id):
#     conn, cursor = None, None
#     try:
#         conn = get_db_connection()
#         cursor = conn.cursor(dictionary=True)
        
#         # First check if the user exists
#         cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
#         user = cursor.fetchone()
        
#         if not user:
#             return jsonify({"success": False, "message": "User not found"})
        
#         # Check if user is trying to delete themselves
#         if user_id == session.get('user_id'):
#             return jsonify({"success": False, "message": "You cannot delete your own account"})
        
#         # Check if user is an admin (prevent deleting other admins)
#         cursor.execute("SELECT role_name FROM roles WHERE role_id = %s", (user['role_id'],))
#         role = cursor.fetchone()
        
#         if role and role['role_name'] == 'admin':
#             return jsonify({"success": False, "message": "Cannot delete admin users"})
        
#         # First delete related records to avoid foreign key constraints
#         cursor.execute("DELETE FROM volunteer_tasks WHERE volunteer_id = %s", (user_id,))
#         cursor.execute("DELETE FROM registrations WHERE participant_id = %s", (user_id,))
#         cursor.execute("DELETE FROM notifications WHERE user_id = %s", (user_id,))
#         cursor.execute("DELETE FROM organizer_requests WHERE user_id = %s", (user_id,))
#         cursor.execute("UPDATE events SET organizer_id = NULL WHERE organizer_id = %s", (user_id,))
        
#         # Now delete the user
#         cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
#         conn.commit()
        
#         return jsonify({"success": True, "message": "User deleted successfully"})
#     except mysql.connector.Error as err:
#         if conn:
#             conn.rollback()
#         return jsonify({"success": False, "message": f"Database error: {str(err)}"})
#     finally:
#         if cursor: 
#             cursor.close()
#         if conn: 
#             conn.close()

# ---------------- Manage Events ----------------


@admin_bp.route("/events")
@admin_required
def events():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get filter, page, and per_page from query parameters
        filter_type = request.args.get('filter', 'all')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 5))
        
        # Base query
        query = """
            SELECT e.*, u.name as organizer_name,
                (SELECT COUNT(*) FROM registrations r WHERE r.event_id = e.event_id) as participant_count,
                (SELECT COUNT(*) FROM volunteer_tasks vt WHERE vt.event_id = e.event_id) as volunteer_count
            FROM events e
            JOIN users u ON e.organizer_id = u.user_id
        """
        # Apply filter
        if filter_type == 'upcoming':
            query += " WHERE e.event_date >= CURDATE()"
        elif filter_type == 'past':
            query += " WHERE e.event_date < CURDATE()"
        
        query += " ORDER BY e.event_date DESC"
        cursor.execute(query)
        all_events = cursor.fetchall()

        # Pagination calculations
        total = len(all_events)
        total_pages = (total + per_page - 1) // per_page
        start = (page - 1) * per_page
        events_paginated = all_events[start:start+per_page]
        today = date.today()
        for e in events_paginated:
            if e['event_date'] > today:
                e['status_display'] = 'upcoming'
            elif e['event_date'] == today:
                e['status_display'] = 'ongoing'
            else:
                e['status_display'] = 'completed'
        # If AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'events': [
                    {
                        'id': e['event_id'],
                        'name': e['title'],
                        'date': str(e['event_date']),
                        'location': e['location'],
                        'participants': e['participant_count'],
                        'capacity': e.get('total_tickets') or e.get('volunteer_required'),
                        'status_display': (
    'upcoming' if e['event_date'] > date.today() else
    'ongoing' if e['event_date'] == date.today() else
    'completed'
),

                        'organizer': e['organizer_name']
                    } for e in events_paginated
                ],
                'page': page,
                'total_pages': total_pages,
                'total': total
            })

        # Server-side render with paginated events
        return render_template(
            "admin_manage_events.html",
            events=events_paginated,
            pagination={
                'page': page,
                'total_pages': total_pages,
                'per_page': per_page,
                'total': total
            },
            filter_type=filter_type
        )

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return render_template(
            "admin_manage_events.html",
            events=[],
            pagination={'page':1,'total_pages':1,'per_page':5,'total':0},
            filter_type='all'
        )
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ---------------- Reports ----------------
@admin_bp.route("/reports")
@admin_required
def reports():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        per_page = 3
        page_top = int(request.args.get("page_top", 1))
        page_demo = int(request.args.get("page_demo", 1))

        # User growth (last 6 months)
        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%Y-%m') as month, 
                   COUNT(*) as count,
                   SUM(COUNT(*)) OVER (ORDER BY DATE_FORMAT(created_at, '%Y-%m')) as cumulative
            FROM users 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
            GROUP BY DATE_FORMAT(created_at, '%Y-%m')
            ORDER BY month
        """)
        user_growth = cursor.fetchall()

        # Event stats
        cursor.execute("SELECT status, COUNT(*) as count FROM events GROUP BY status")
        event_stats = cursor.fetchall()

        # --- Top Events (with pagination) ---
        cursor.execute("""
            SELECT SQL_CALC_FOUND_ROWS
                   e.title, COUNT(r.reg_id) as participants,
                   CASE 
                     WHEN e.volunteer_required > 0 THEN 
                       ROUND(COUNT(r.reg_id) / e.volunteer_required * 100, 0)
                     ELSE 0 
                   END as completion_rate
            FROM events e
            LEFT JOIN registrations r 
                   ON e.event_id = r.event_id 
                  AND r.status IN ('registered', 'attended')
            GROUP BY e.event_id
            ORDER BY participants DESC
            LIMIT %s OFFSET %s
        """, (per_page, (page_top - 1) * per_page))
        top_events = cursor.fetchall()

        cursor.execute("SELECT FOUND_ROWS() as total")
        total_top = cursor.fetchone()["total"]
        total_top_pages = (total_top + per_page - 1) // per_page

        # --- User Demographics (with pagination) ---
        # Total roles for pagination
        cursor.execute("SELECT COUNT(*) as total FROM roles")
        total_demo = cursor.fetchone()["total"]
        total_demo_pages = (total_demo + per_page - 1) // per_page

        # Fetch paginated data
        cursor.execute("""
            SELECT r.role_name, COUNT(u.user_id) as count,
                   ROUND(COUNT(u.user_id) / (SELECT COUNT(*) FROM users) * 100, 1) as percentage
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            GROUP BY r.role_name
            ORDER BY count DESC
            LIMIT %s OFFSET %s
        """, (per_page, (page_demo - 1) * per_page))
        user_demographics = cursor.fetchall()

        return render_template(
            "admin_reports.html", 
            user_growth=user_growth,
            event_stats=event_stats,
            top_events=top_events,
            user_demographics=user_demographics,
            # pagination context
            page_top=page_top,
            total_top_pages=total_top_pages,
            page_demo=page_demo,
            total_demo_pages=total_demo_pages,
            # template condition
            has_user_demographics=len(user_demographics) > 0
        )

    except Exception as e:
        flash(f"An error occurred: {e}", "danger")
        return render_template("admin_reports.html", 
                              user_growth=[], event_stats=[], top_events=[], user_demographics=[],
                              page_top=1, total_top_pages=1, page_demo=1, total_demo_pages=1,
                              has_user_demographics=False)
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

import csv
import io
from flask import make_response

# ---------------- Generate Report (Download) ----------------
@admin_bp.route("/generate_report")
@admin_required
def generate_report():
    conn, cursor = None, None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Example: Get users with their roles
        cursor.execute("""
            SELECT u.user_id, u.name, u.email, r.role_name, u.created_at
            FROM users u
            JOIN roles r ON u.role_id = r.role_id
            ORDER BY u.created_at DESC
        """)
        users = cursor.fetchall()

        # Use StringIO as in-memory file
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["User ID", "Name", "Email", "Role", "Created At"])

        # Write data rows
        for u in users:
            writer.writerow([
                u["user_id"], u["name"], u["email"],
                u["role_name"], u["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            ])

        # Prepare response
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = "attachment; filename=users_report.csv"
        response.headers["Content-Type"] = "text/csv"
        return response

    except Exception as e:
        flash(f"Error generating report: {str(e)}", "danger")
        return redirect(url_for("admin.reports"))
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# ---------------- Organizer Requests ----------------
@admin_bp.route("/organizer_requests")
@admin_required
def organizer_requests():
    search_query = request.args.get("q", "").strip()

    # pagination params
    page_pending = request.args.get("page_pending", 1, type=int)
    page_processed = request.args.get("page_processed", 1, type=int)
    per_page = 5  # items per page

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ==============================
        # Pending requests with COUNT
        # ==============================
        if search_query:
            count_query = """
                SELECT COUNT(*) as total
                FROM organizer_requests r
                JOIN users u ON r.user_id = u.user_id
                WHERE (r.status IS NULL OR r.status = 'pending')
                AND (u.name LIKE %s OR u.email LIKE %s OR r.organization LIKE %s)
            """
            cursor.execute(count_query, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
            total_pending = cursor.fetchone()["total"]

            cursor.execute("""
                SELECT r.request_id, r.user_id, r.status, r.request_date, r.processed_date,
                       r.organization, r.photo_path, r.reason,
                       u.name, u.email, u.created_at as user_created,
                       p.name as processed_by_name
                FROM organizer_requests r
                JOIN users u ON r.user_id = u.user_id
                LEFT JOIN users p ON r.processed_by = p.user_id
                WHERE (r.status IS NULL OR r.status = 'pending')
                AND (u.name LIKE %s OR u.email LIKE %s OR r.organization LIKE %s)
                ORDER BY r.request_date DESC
                LIMIT %s OFFSET %s
            """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", per_page, (page_pending - 1) * per_page))
        else:
            cursor.execute("SELECT COUNT(*) as total FROM organizer_requests WHERE status IS NULL OR status = 'pending'")
            total_pending = cursor.fetchone()["total"]

            cursor.execute("""
                SELECT r.request_id, r.user_id, r.status, r.request_date, r.processed_date,
                       r.organization, r.photo_path, r.reason,
                       u.name, u.email, u.created_at as user_created,
                       p.name as processed_by_name
                FROM organizer_requests r
                JOIN users u ON r.user_id = u.user_id
                LEFT JOIN users p ON r.processed_by = p.user_id
                WHERE r.status IS NULL OR r.status = 'pending'
                ORDER BY r.request_date DESC
                LIMIT %s OFFSET %s
            """, (per_page, (page_pending - 1) * per_page))
        pending_requests = cursor.fetchall()

        # ==============================
        # Processed requests with COUNT
        # ==============================
        if search_query:
            count_query = """
                SELECT COUNT(*) as total
                FROM organizer_requests r
                JOIN users u ON r.user_id = u.user_id
                WHERE r.status IN ('approved', 'rejected')
                AND (u.name LIKE %s OR u.email LIKE %s OR r.organization LIKE %s)
            """
            cursor.execute(count_query, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"))
            total_processed = cursor.fetchone()["total"]

            cursor.execute("""
                SELECT r.request_id, r.user_id, r.status, r.request_date, r.processed_date,
                       r.organization, r.photo_path, r.reason,
                       u.name as user_name, u.email,
                       p.name as processed_by_name
                FROM organizer_requests r
                JOIN users u ON r.user_id = u.user_id
                LEFT JOIN users p ON r.processed_by = p.user_id
                WHERE r.status IN ('approved', 'rejected')
                AND (u.name LIKE %s OR u.email LIKE %s OR r.organization LIKE %s)
                ORDER BY r.processed_date DESC
                LIMIT %s OFFSET %s
            """, (f"%{search_query}%", f"%{search_query}%", f"%{search_query}%", per_page, (page_processed - 1) * per_page))
        else:
            cursor.execute("SELECT COUNT(*) as total FROM organizer_requests WHERE status IN ('approved','rejected')")
            total_processed = cursor.fetchone()["total"]

            cursor.execute("""
                SELECT r.request_id, r.user_id, r.status, r.request_date, r.processed_date,
                       r.organization, r.photo_path, r.reason,
                       u.name as user_name, u.email,
                       p.name as processed_by_name
                FROM organizer_requests r
                JOIN users u ON r.user_id = u.user_id
                LEFT JOIN users p ON r.processed_by = p.user_id
                WHERE r.status IN ('approved', 'rejected')
                ORDER BY r.processed_date DESC
                LIMIT %s OFFSET %s
            """, (per_page, (page_processed - 1) * per_page))
        processed_requests = cursor.fetchall()

        # calculate total pages
        total_pending_pages = (total_pending + per_page - 1) // per_page
        total_processed_pages = (total_processed + per_page - 1) // per_page

        return render_template(
            "admin_organizer_requests.html", 
            pending_requests=pending_requests,
            processed_requests=processed_requests,
            search_query=search_query,
            page_pending=page_pending,
            total_pending_pages=total_pending_pages,
            page_processed=page_processed,
            total_processed_pages=total_processed_pages
        )

    except Exception as e:
        flash(f"Error fetching organizer requests: {str(e)}", "danger")
        return render_template(
            "admin_organizer_requests.html", 
            pending_requests=[],
            processed_requests=[],
            search_query=search_query,
            page_pending=1,
            total_pending_pages=0,
            page_processed=1,
            total_processed_pages=0
        )
    finally:
        if cursor: cursor.close()
        if conn: conn.close()



# ==============================
# Approve Organizer Request
# ==============================
@admin_bp.route("/approve_organizer_request/<int:request_id>", methods=["POST"])
@admin_required
def approve_organizer_request(request_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get the request
        cursor.execute("SELECT user_id FROM organizer_requests WHERE request_id=%s", (request_id,))
        req = cursor.fetchone()
        if not req:
            flash("Request not found.", "danger")
            return redirect(url_for("admin.organizer_requests"))

        user_id = req["user_id"]

        # Get organizer role_id
        cursor.execute("SELECT role_id FROM roles WHERE role_name='organizer'")
        role_row = cursor.fetchone()
        if not role_row:
            flash("Organizer role not found in roles table.", "danger")
            return redirect(url_for("admin.organizer_requests"))

        role_id = role_row["role_id"]

        # Update user role
        cursor.execute("UPDATE users SET role_id=%s WHERE user_id=%s", (role_id, user_id))

        # Update request
        admin_id = session.get("user_id") if session.get("user_id") else None
        cursor.execute("""
            UPDATE organizer_requests 
            SET status='approved', processed_date=NOW(), processed_by=%s
            WHERE request_id=%s
        """, (admin_id, request_id))

        conn.commit()

        # 🔄 If the approved user is the logged-in one, update session instantly
        if session.get("user_id") == user_id:
            session["role"] = "organizer"

        flash("Organizer request approved successfully!", "success")

    except Exception as e:
        if conn: conn.rollback()
        flash(f"Error approving request: {str(e)}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for("admin.organizer_requests"))


# ==============================
# Reject Organizer Request
# ==============================
@admin_bp.route("/reject_organizer_request/<int:request_id>", methods=["POST"])
@admin_required
def reject_organizer_request(request_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        admin_id = session.get("user_id") if session.get("user_id") else None

        # Update request
        cursor.execute("""
            UPDATE organizer_requests 
            SET status='rejected', processed_date=NOW(), processed_by=%s
            WHERE request_id=%s
        """, (admin_id, request_id))

        # Get rejected user for session sync
        cursor.execute("SELECT user_id FROM organizer_requests WHERE request_id=%s", (request_id,))
        req = cursor.fetchone()

        conn.commit()

        # 🔄 If rejected user is logged in, downgrade role instantly
        if req and session.get("user_id") == req["user_id"]:
            session["role"] = "user"

        flash("Organizer request rejected.", "info")

    except Exception as e:
        if conn: conn.rollback()
        flash(f"Error rejecting request: {str(e)}", "danger")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

    return redirect(url_for("admin.organizer_requests"))
# Active or Inactive

@admin_bp.route("/toggle_user/<int:user_id>", methods=["POST"])
def toggle_user_status(user_id):
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ("active", "inactive"):
        return jsonify({"success": False, "message": "Invalid status"}), 400
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status=%s WHERE user_id=%s", (new_status, user_id))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "new_status": new_status})


@admin_bp.route("/profile")
@admin_required
def profile():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT user_id, name, email FROM users WHERE user_id=%s", (user_id,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    if not admin:
        flash("Admin not found in database.", "danger")
        return redirect(url_for("auth.login"))

    return render_template("admin_profile.html", admin=admin)


#============================
# EDIT PROFILE
#============================
# admin/routes.py
@admin_bp.route("/edit", methods=["GET", "POST"])
@admin_required
def edit_profile():
    user_id = session.get("user_id")

    if not user_id:
        return redirect(url_for("auth.login"))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form.get("phone")
        bio = request.form.get("bio")

        cursor.execute("""
            UPDATE users 
            SET name=%s, email=%s, phone=%s, bio=%s
            WHERE user_id=%s
        """, (name, email, phone, bio, user_id))
        conn.commit()

        flash("Profile updated successfully!", "success")
        return redirect(url_for("admin.profile"))

    # Fetch current admin details
    cursor.execute("SELECT user_id, name, email, phone, bio FROM users WHERE user_id=%s", (user_id,))
    admin = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template("edit_profile.html", admin=admin)

