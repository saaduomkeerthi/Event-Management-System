from werkzeug.security import generate_password_hash, check_password_hash
from models.db import get_db_connection


# -------------------------------
# Create default Admin role + user
# -------------------------------
def create_default_admin():
    conn = get_db_connection()
    if conn is None:
        print("❌ No DB connection.")
        return

    cursor = conn.cursor(dictionary=True)

    # Step 1: Ensure "admin" role exists
    cursor.execute("SELECT role_id FROM roles WHERE role_name = %s", ("admin",))
    role = cursor.fetchone()

    if not role:
        cursor.execute("INSERT INTO roles (role_name) VALUES (%s)", ("admin",))
        conn.commit()
        cursor.execute("SELECT role_id FROM roles WHERE role_name = %s", ("admin",))
        role = cursor.fetchone()

    admin_role_id = role["role_id"]

    # Step 2: Ensure default admin user exists
    cursor.execute(
        "SELECT * FROM users WHERE email = %s", ("admin@gmail.com",)
    )
    admin = cursor.fetchone()

    if not admin:
        default_email = "admin@gmail.com"
        default_password = "admin123"
        hashed_password = generate_password_hash(default_password)

        cursor.execute(
            """
            INSERT INTO users (name, email, password_hash, role_id)
            VALUES (%s, %s, %s, %s)
            """,
            ("System Admin", default_email, hashed_password, admin_role_id),
        )

        conn.commit()
        print(f"✅ Default admin created: {default_email} / {default_password}")
    else:
        print("ℹ️ Admin already exists. Skipping initialization.")

    cursor.close()
    conn.close()


# -------------------------------
# Validate user login
# -------------------------------
def validate_user(email, password):
    conn = get_db_connection()
    if conn is None:
        return None

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    # If user found, check password
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None