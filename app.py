from flask import Flask, render_template
from models.user import create_default_admin
from auth.routes import auth_bp
from admin.routes import admin_bp
from organizer.routes import organizer_bp
from volunteer.routes import volunteer_bp
from participant.routes import participant_bp

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Register Blueprints without a URL prefix
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(admin_bp, url_prefix="/admin")
app.register_blueprint(organizer_bp, url_prefix='/organizer')
app.register_blueprint(volunteer_bp, url_prefix='/volunteer')
app.register_blueprint(participant_bp, url_prefix='/participant')
from models.db import get_db_connection
@app.route("/")
# routes.py or app.py
@app.route("/")
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT title, description, image_url
        FROM events
        ORDER BY created_at DESC
        LIMIT 3
    """)
    latest_events = cursor.fetchall()  # returns list of tuples/dicts
    return render_template("index.html", latest_events=latest_events)


@app.route("/contact")
def contact():
    return render_template("contact.html")

if __name__ == "__main__":
    create_default_admin()
    app.run(debug=True)
