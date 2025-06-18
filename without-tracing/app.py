# app.py

import os
import sqlite3
import time
import threading
from datetime import datetime

from flask import Flask, Response
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST

# Initialize Flask app
app = Flask(__name__)

# --- Database Configuration ---
# Read DB_NAME from environment variable, defaulting to in-memory SQLite if not set.
# For a real OpenShift deployment with persistent storage, change ':memory:' to a file path
# like '/data/timestamps.db' and ensure a Persistent Volume Claim is mounted to /data.
# For an external database, this would be the database name on the server.
DB_NAME = os.getenv('DB_NAME', ':memory:')

# Read database credentials from environment variables.
# These will be populated by OpenShift Secrets.
# Uncomment and provide default values if you want to test locally without secrets.
DB_USER = os.getenv('DB_USER') # e.g., 'myuser'
DB_PASSWORD = os.getenv('DB_PASSWORD') # e.g., 'my_secure_password'
DB_HOST = os.getenv('DB_HOST') # e.g., 'your-db-service.your-project.svc.cluster.local'
DB_PORT = os.getenv('DB_PORT') # e.g., '5432' for PostgreSQL

# Read write interval from environment variable, default to 5 seconds.
try:
    DB_WRITE_INTERVAL_SECONDS = int(os.getenv('DB_WRITE_INTERVAL_SECONDS', 5))
except ValueError:
    print("Warning: DB_WRITE_INTERVAL_SECONDS environment variable is not an integer. Using default 5 seconds.")
    DB_WRITE_INTERVAL_SECONDS = 5

# --- Prometheus Metrics Initialization ---
# Histogram metric for database write latency (seconds)
# Define custom buckets for more granular latency distribution analysis.
# For example, you might want finer buckets for low latencies.
DB_WRITE_LATENCY = Histogram(
    'db_write_latency_seconds',
    'Latency of database write operations to the timestamps table.',
    buckets=(.005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0, 10.0, float('inf'))
)

# Counter metric for total successful database write operations
DB_WRITE_SUCCESS_TOTAL = Counter(
    'db_write_success_total',
    'Total count of successful database write operations.'
)

# Counter metric for total failed database write operations
DB_WRITE_FAILURE_TOTAL = Counter(
    'db_write_failure_total',
    'Total count of failed database write operations.'
)

# Counter metric for database write operations that timed out (simulated)
DB_WRITE_TIMEOUT_TOTAL = Counter(
    'db_write_timeout_total',
    'Total count of database write operations that timed out (simulated).'
)

# --- Database Functions ---

def get_db_connection():
    """
    Establishes and returns a database connection.
    This function needs to be adapted for your specific external database (e.g., PostgreSQL, MySQL).
    """
    if DB_NAME == ':memory:' or not DB_NAME.endswith('.db'):
        # Using SQLite (in-memory or file-based)
        print(f"Connecting to SQLite database: {DB_NAME}")
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        return conn
    else:
        # Example for an external database like PostgreSQL (requires 'psycopg2' library)
        # You would typically install psycopg2 via pip and import it here.
        # import psycopg2
        # try:
        #     print(f"Connecting to external database: {DB_HOST}:{DB_PORT}/{DB_NAME} as {DB_USER}")
        #     conn = psycopg2.connect(
        #         host=DB_HOST,
        #         port=DB_PORT,
        #         user=DB_USER,
        #         password=DB_PASSWORD,
        #         database=DB_NAME
        #     )
        #     return conn
        # except Exception as e:
        #     print(f"Error connecting to external database: {e}")
        #     raise # Re-raise to ensure the error is handled upstream
        print("WARNING: External database connection not implemented in this example.")
        print("Please replace SQLite connection with your actual database driver and connection logic.")
        # Fallback to in-memory SQLite for demonstration if no proper external DB config
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        return conn


def create_table():
    """Creates the timestamps table if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # This SQL is for SQLite. Adapt for other databases (e.g., SERIAL for PostgreSQL)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timestamps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        print(f"Database table 'timestamps' ensured to exist in '{DB_NAME}'.")
    except Exception as e:
        print(f"Error creating database table: {e}")

def write_timestamp_to_db():
    """
    Writes the current timestamp to the database and records Prometheus metrics.
    Includes simulated timeout and general failure scenarios.
    """
    with DB_WRITE_LATENCY.time(): # Measure the duration of this block
        try:
            # Simulate a timeout or failure occasionally for demonstration.
            # In a real scenario, network issues or DB server unresponsiveness
            # would lead to actual timeouts caught by your DB driver.
            if os.getenv('SIMULATE_DB_FAILURE', 'false').lower() == 'true' and \
               datetime.now().second % 10 == 0: # Simulate failure every 10 seconds
                raise sqlite3.OperationalError("Simulated database connection error or timeout")

            conn = get_db_connection()
            cursor = conn.cursor()
            current_time = datetime.now().isoformat()
            cursor.execute("INSERT INTO timestamps (timestamp) VALUES (?)", (current_time,))
            conn.commit()
            conn.close()
            DB_WRITE_SUCCESS_TOTAL.inc()
            print(f"Timestamp '{current_time}' written successfully to '{DB_NAME}'.")

        except (sqlite3.OperationalError, Exception) as e:
            # Broad exception catch for demonstration.
            # In production, differentiate specific database exceptions.
            if "timeout" in str(e).lower() or "operationalerror" in str(e).lower():
                DB_WRITE_TIMEOUT_TOTAL.inc() # Treat specific operational errors/timeouts as such
                print(f"Database write failed (simulated timeout/operational error): {e}")
            else:
                print(f"Database write failed (general error): {e}")
            DB_WRITE_FAILURE_TOTAL.inc() # Increment total failures for any error

# --- Periodic Background Task ---
def periodic_db_writer():
    """
    Background thread function to periodically write timestamps to the database.
    """
    while True:
        write_timestamp_to_db()
        time.sleep(DB_WRITE_INTERVAL_SECONDS)

# --- Flask Routes ---

@app.route('/')
def health_check():
    """Simple health check endpoint."""
    return "Flask app is running and writing timestamps!", 200

@app.route('/metrics')
def metrics():
    """
    Endpoint for Prometheus to scrape metrics.
    Returns the latest metrics in Prometheus exposition format.
    """
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# --- Application Startup ---
if __name__ == '__main__':
    # Ensure the database table exists on startup
    create_table()

    # Start the background thread for periodic database writes
    # Setting daemon=True ensures the thread exits when the main program exits
    db_writer_thread = threading.Thread(target=periodic_db_writer, daemon=True)
    db_writer_thread.start()

    # Run the Flask application
    # 0.0.0.0 makes the server accessible from outside the container
    # Port 5000 is a common default for Flask apps
    app.run(host='0.0.0.0', port=5000)
