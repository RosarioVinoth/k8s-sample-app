# app.py

import os
import time
import threading
from datetime import datetime
import logging # Import the logging module

from flask import Flask, Response
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST

# --- PostgreSQL Import ---
import psycopg2
from psycopg2 import OperationalError as Psycopg2OperationalError # Alias to avoid conflict with sqlite3.OperationalError


# Initialize Flask app
app = Flask(__name__)

# --- Configure Flask Logging ---
# Set up a basic logging configuration for the Flask app.
# This ensures application messages are properly emitted.
# Logs will go to stdout, which Kubernetes/OpenShift captures.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO) # Set default level for app.logger

# --- Database Configuration ---
# Read DB_NAME from environment variable. For PostgreSQL, this is the database name.
DB_NAME = os.getenv('DB_NAME') # This should now be mandatory for an external DB

# Read database credentials from environment variables.
# These will be populated by OpenShift Secrets.
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT') # Defaults to string, psycopg2 expects string or int.

# Validate essential PostgreSQL connection parameters
if not all([DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT]):
    app.logger.error("ERROR: Missing one or more PostgreSQL connection environment variables (DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT). Exiting.")
    # In a real app, you might want to raise an exception or exit more gracefully.
    exit(1)


# Read write interval from environment variable, default to 5 seconds.
try:
    DB_WRITE_INTERVAL_SECONDS = int(os.getenv('DB_WRITE_INTERVAL_SECONDS', 5))
except ValueError:
    app.logger.warning("DB_WRITE_INTERVAL_SECONDS environment variable is not an integer. Using default 5 seconds.")
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
    Establishes and returns a PostgreSQL database connection.
    Uses environment variables for connection parameters.
    """
    try:
        app.logger.info(f"Connecting to PostgreSQL database: {DB_USER}@tcp({DB_HOST}:{DB_PORT})/{DB_NAME}")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            connect_timeout=5 # Set a connection timeout (e.g., 5 seconds)
        )
        return conn
    except Psycopg2OperationalError as e:
        app.logger.error(f"PostgreSQL connection failed (OperationalError): {e}")
        raise # Re-raise to ensure the error is handled upstream
    except Exception as e:
        app.logger.error(f"Error connecting to PostgreSQL database: {e}")
        raise # Re-raise to ensure the error is handled upstream


def create_table():
    """Creates the timestamps table if it doesn't exist in PostgreSQL."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # PostgreSQL specific SQL for auto-incrementing ID
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timestamps (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        app.logger.info(f"Database table 'timestamps' ensured to exist in PostgreSQL database '{DB_NAME}'.")
    except Exception as e:
        app.logger.error(f"Error creating database table in PostgreSQL: {e}")
        # Depending on the error, you might want to exit if table creation is critical.
        # For now, we'll let the app continue if it's a transient error.

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
                raise Psycopg2OperationalError("Simulated database connection error or timeout")

            conn = get_db_connection()
            cursor = conn.cursor()
            current_time = datetime.now().isoformat()
            cursor.execute("INSERT INTO timestamps (timestamp) VALUES (%s)", (current_time,)) # Use %s for psycopg2 placeholders
            conn.commit()
            conn.close()
            DB_WRITE_SUCCESS_TOTAL.inc()
            app.logger.info(f"Timestamp '{current_time}' written successfully to '{DB_NAME}'.")

        except Psycopg2OperationalError as e:
            # Catch PostgreSQL specific operational errors (e.g., connection issues, timeouts)
            DB_WRITE_TIMEOUT_TOTAL.inc() # Treat operational errors as timeouts for this example
            DB_WRITE_FAILURE_TOTAL.inc()
            app.logger.error(f"PostgreSQL write failed (operational error/timeout): {e}")
        except Exception as e:
            DB_WRITE_FAILURE_TOTAL.inc()
            app.logger.error(f"Database write failed (general error): {e}")
        finally:
            # Ensure connection is closed even if an error occurs
            if 'conn' in locals() and conn:
                conn.close()


# --- Periodic Background Task ---
def periodic_db_writer():
    """
    Background thread function to periodically write timestamps to the database.
    """
    while True:
        # In case get_db_connection() fails during startup, give it a moment
        try:
            write_timestamp_to_db()
        except Exception as e:
            app.logger.error(f"Periodic DB writer encountered a non-recoverable error during write: {e}. Retrying after interval.")
            # Do not re-raise, allow the loop to continue and retry.
        time.sleep(DB_WRITE_INTERVAL_SECONDS)

# --- Flask Routes ---

@app.route('/')
def health_check():
    """Simple health check endpoint."""
    app.logger.info("Health check endpoint accessed.")
    return "Flask app is running and writing timestamps!", 200

@app.route('/metrics')
def metrics():
    """
    Endpoint for Prometheus to scrape metrics.
    Returns the latest metrics in Prometheus exposition format.
    """
    app.logger.debug("Metrics endpoint accessed by Prometheus.") # Use debug level for frequent access
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# --- Application Startup ---
if __name__ == '__main__':
    # Ensure the database table exists on startup
    # This assumes the connection parameters are available and correct at startup.
    app.logger.info("Starting Flask application...")
    create_table()

    # Start the background thread for periodic database writes
    # Setting daemon=True ensures the thread exits when the main program exits
    db_writer_thread = threading.Thread(target=periodic_db_writer, daemon=True)
    db_writer_thread.start()

    # Run the Flask application
    # 0.0.0.0 makes the server accessible from outside the container
    # Port 5000 is a common default for Flask apps
    app.run(host='0.0.0.0', port=5000)
