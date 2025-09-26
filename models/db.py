import mysql.connector
from mysql.connector import Error
from config import Config

def get_db_connection():
    """
    Create and return a new database connection.
    Caller must close it after use.
    """
    try:
        conn = mysql.connector.connect(
            host=Config.DB_HOST,
            port=Config.DB_PORT,
            user=Config.DB_USER,
            password=Config.DB_PASS,
            database=Config.DB_NAME
        )
        if conn.is_connected():
            print("✅ Database connected successfully")
            return conn
    except Error as e:
        print(f"❌ Database connection error: {e}")
        return None
