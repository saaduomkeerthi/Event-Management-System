from flask import (
    Blueprint, render_template, request, redirect, 
    url_for, session, flash, Response
)
from werkzeug.security import check_password_hash, generate_password_hash
from models.db import get_db_connection
from captcha.image import ImageCaptcha
import random, string, io
from functools import wraps
from werkzeug.utils import secure_filename
import os, uuid




# ==============================
# Blueprint
# ==============================
auth_bp = Blueprint("auth", __name__, template_folder="templates")

# ==============================
# Config
# ==============================
ADMIN_CREDENTIALS = {
    "email": "admin@gmail.com",
    "password": "admin123"
}

UPLOAD_FOLDER = os.path.join("static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ==============================
# Login Required Decorator
# ==============================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            flash("Please log in to access this page.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# ==============================
# Login
# ==============================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        captcha_input = request.form.get("captcha", "").strip()

        # ✅ Validate captcha
        if "captcha_text" not in session or captcha_input.upper() != session["captcha_text"]:
            flash("Invalid CAPTCHA. Please try again.", "danger")
            return redirect(url_for("auth.login"))

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # ✅ Fetch user + role info from DB
            cursor.execute("""
                SELECT u.*, r.role_name 
                FROM users u 
                JOIN roles r ON u.role_id = r.role_id 
                WHERE u.email=%s
            """, (email,))
            user = cursor.fetchone()

            if user:
                # 🚨 Check if account is inactive
                if user["status"].lower() != "active":
                    flash("Your account is inactive. Please contact admin.", "danger")
                    return redirect(url_for("auth.login"))

                # ✅ Verify password
                if check_password_hash(user["password_hash"], password):
                    # Store session data
                    session["user"] = user["email"]
                    session["user_id"] = user["user_id"]
                    session["name"] = user["name"]
                    session["profile_picture"] = user.get("profile_picture")
                    session["role"] = user["role_name"].lower()
                    session["is_admin"] = (session["role"] == "admin")
                    session["is_volunteer"] = user.get("is_volunteer", False)

                    flash(f"Welcome back, {user['role_name'].capitalize()}!", "success")

                    # Redirect based on role
                    if session["is_admin"]:
                        return redirect(url_for("admin.dashboard"))
                    elif session["role"] == "organizer":
                        return redirect(url_for("organizer.dashboard"))
                    elif session["is_volunteer"]:
                        return redirect(url_for("volunteer.dashboard"))
                    elif session["role"] == "participant":
                        return redirect(url_for("participant.dashboard"))
                    else:
                        return redirect(url_for("index"))
                else:
                    flash("Invalid credentials", "danger")
                    return redirect(url_for("auth.login"))
            else:
                flash("Invalid credentials", "danger")
                return redirect(url_for("auth.login"))

        except Exception as e:
            flash(f"An error occurred: {e}", "danger")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template("login.html")



# ==============================
# Participant Signup
# ==============================
@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]
        captcha_input = request.form.get("captcha", "").strip()
        
        # Validate captcha
        if 'captcha_text' not in session or captcha_input.upper() != session['captcha_text']:
            flash("Invalid CAPTCHA. Please try again.", "danger")
            return redirect(url_for("auth.signup"))

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if email already exists
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            if cursor.fetchone():
                flash("Email already exists. Please use a different email.", "danger")
                return redirect(url_for("auth.signup"))
            
            # Get participant role ID (default)
            cursor.execute("SELECT role_id FROM roles WHERE role_name='participant'")
            role_id = cursor.fetchone()[0]
            
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, role_id) VALUES (%s, %s, %s, %s)",
                (name, email, generate_password_hash(password), role_id)
            )
            conn.commit()
            flash("Account created! Please login.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"An error occurred while creating your account: {e}", "danger")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template("signup.html")

# ==============================
# Organizer Signup
# ==============================

# Upload folder setup
UPLOAD_FOLDER = os.path.join("static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@auth_bp.route("/organizer_signup", methods=["GET", "POST"])
def organizer_signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        organization = request.form.get("organization")
        reason = request.form.get("reason")
        photo = request.files.get("photo")

        # ✅ Hash password
        password_hash = generate_password_hash(password)

        # ✅ Save uploaded photo
        photo_path = None
        if photo and allowed_file(photo.filename):
            filename = f"{uuid.uuid4()}_{secure_filename(photo.filename)}"
            photo_path = os.path.join(UPLOAD_FOLDER, filename)
            photo.save(photo_path)
            photo_path = f"uploads/{filename}"  # relative path for templates

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            # 1️⃣ Insert user into users (role_id NULL until admin approves)
            cursor.execute(
                """
                INSERT INTO users (name, email, password_hash, role_id, organization)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (name, email, password_hash, None, organization)
            )
            user_id = cursor.lastrowid

            # 2️⃣ Insert request into organizer_requests
            cursor.execute(
                """
                INSERT INTO organizer_requests (user_id, organization, photo_path, reason)
                VALUES (%s, %s, %s, %s)
                """,
                (user_id, organization, photo_path, reason)
            )

            conn.commit()
            flash("Organizer signup request submitted successfully! Pending admin approval.", "success")
            return redirect(url_for("auth.login"))

        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"Error: {str(e)}", "danger")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template("organizer_signup.html")



# ==============================
# Captcha
# ==============================
@auth_bp.route("/generate_captcha")
def generate_captcha():
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    session['captcha_text'] = captcha_text
    image = ImageCaptcha(width=280, height=90)
    out = io.BytesIO()
    image.write(captcha_text, out)
    out.seek(0)
    return Response(out.read(), mimetype='image/png')

# ==============================
# Logout
# ==============================
@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))
# ==============================
# Volunteer Signup
# ==============================
@auth_bp.route("/volunteer_signup", methods=["GET", "POST"])
def volunteer_signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        phone = request.form.get("phone")
        skills = request.form.getlist("skills")  # For multiple select
        availability = request.form.getlist("availability")  # For checkboxes
        emergency_contact = request.form.get("emergency_contact")
        
        # Validate passwords match
        if password != confirm_password:
            flash("Passwords do not match!", "danger")
            return redirect(url_for("auth.volunteer_signup"))
        
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if email already exists
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            if cursor.fetchone():
                flash("Email already exists. Please use a different email.", "danger")
                return redirect(url_for("auth.volunteer_signup"))
            
            # Get or create volunteer role
            cursor.execute("SELECT role_id FROM roles WHERE role_name='volunteer'")
            role_result = cursor.fetchone()
            if not role_result:
                # Create volunteer role if it doesn't exist
                cursor.execute("INSERT INTO roles (role_name) VALUES ('volunteer')")
                conn.commit()
                cursor.execute("SELECT role_id FROM roles WHERE role_name='volunteer'")
                role_result = cursor.fetchone()
                
            role_id = role_result[0]
            
            # Insert user into users table with volunteer info
            cursor.execute(
                """INSERT INTO users 
                (name, email, password_hash, role_id, phone, skills, availability, emergency_contact, is_volunteer) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (name, email, generate_password_hash(password), role_id, phone, 
                 ','.join(skills) if skills else None, 
                 ','.join(availability) if availability else None, 
                 emergency_contact, True)
            )
            
            conn.commit()
            flash("Volunteer account created successfully! Please login.", "success")
            return redirect(url_for("auth.login"))
            
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"An error occurred while creating your account: {e}", "danger")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template("volunteer_signup.html")
# ==============================
# Participant Signup (Dedicated Route)
# ==============================
@auth_bp.route("/participant_signup", methods=["GET", "POST"])
def participant_signup():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]        

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Check if email already exists
            cursor.execute("SELECT * FROM users WHERE email=%s", (email,))
            if cursor.fetchone():
                flash("Email already exists. Please use a different email.", "danger")
                return redirect(url_for("auth.participant_signup"))
            
            # Get participant role ID
            cursor.execute("SELECT role_id FROM roles WHERE role_name='participant'")
            role_id = cursor.fetchone()[0]
            
            cursor.execute(
                "INSERT INTO users (name, email, password_hash, role_id) VALUES (%s, %s, %s, %s)",
                (name, email, generate_password_hash(password), role_id)
            )
            conn.commit()
            flash("Participant account created! Please login.", "success")
            return redirect(url_for("auth.login"))
        except Exception as e:
            if conn:
                conn.rollback()
            flash(f"An error occurred while creating your account: {e}", "danger")
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    return render_template("participant_signup.html")
