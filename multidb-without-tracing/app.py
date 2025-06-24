# app.py

import os
import time
import threading
import json # Still needed for logging/debugging JSON representation, but not for parsing main config
from datetime import datetime
import logging

from flask import Flask, Response
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST

# --- PostgreSQL Import ---
import psycopg2
from psycopg2 import OperationalError as Psycopg2OperationalError


# Initialize Flask app
app = Flask(__name__)

# --- Configure Flask Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO)

# --- Database Configuration ---
# Read a comma-separated list of logical database names from environment variable.
# Example: DATABASE_NAMES="db1,db2,my_analytics_db"
DATABASE_NAMES_STR = os.getenv('DATABASE_NAMES')

# List to hold parsed database configurations
DB_CONFIGS = []

if DATABASE_NAMES_STR:
    database_names = [name.strip() for name in DATABASE_NAMES_STR.split(',') if name.strip()]
    if not database_names:
        app.logger.error("ERROR: DATABASE_NAMES environment variable is set but empty. Exiting.")
        exit(1)

    for db_logical_name in database_names:
        # Convert logical name to uppercase for environment variable lookup convention
        env_prefix = db_logical_name.upper()

        db_config = {
            'name': db_logical_name, # Use the original logical name for the 'name' field
            'host': os.getenv(f'{env_prefix}_DB_HOST'),
            # Hardcode default port to 5432, but allow override from environment variable
            'port': os.getenv(f'{env_prefix}_DB_PORT', '5432'),
            # Hardcode default user to 'k8sadmin', but allow override from environment variable
            'user': os.getenv(f'{env_prefix}_DB_USER', 'k8sadmin'),
            'password': os.getenv(f'{env_prefix}_DB_PASSWORD'),
            # Hardcode default dbname to 'timestamps', but allow override from environment variable
            'dbname': os.getenv(f'{env_prefix}_DB_DBNAME', 'timestamp')
        }

        # Validate essential PostgreSQL connection parameters.
        # 'host' and 'password' are now mandatory.
        # 'port', 'user', and 'dbname' now have defaults.
        required_keys = ['host', 'password']
        if not all(db_config.get(key) for key in required_keys):
            app.logger.error(f"ERROR: Missing one or more required environment variables for database '{db_logical_name}'. Expected: "
                             f"'{env_prefix}_DB_HOST', '{env_prefix}_DB_PASSWORD'. "
                             f"'PORT', 'USER', and 'DBNAME' have defaults but can be overridden. Exiting.")
            exit(1)
        DB_CONFIGS.append(db_config)
        app.logger.info(f"Loaded database configuration for: {db_logical_name}")
else:
    app.logger.error("ERROR: DATABASE_NAMES environment variable not set. Please provide a comma-separated list of logical database names. Exiting.")
    exit(1)

# Read write interval from environment variable, default to 5 seconds.
try:
    DB_WRITE_INTERVAL_SECONDS = int(os.getenv('DB_WRITE_INTERVAL_SECONDS', 5))
except ValueError:
    app.logger.warning("DB_WRITE_INTERVAL_SECONDS environment variable is not an integer. Using default 5 seconds.")
    DB_WRITE_INTERVAL_SECONDS = 5

# --- Prometheus Metrics Initialization ---
DB_WRITE_LATENCY = Histogram(
    'multidb_write_latency_seconds',
    'Latency of database write operations to the timestamps table per database.',
    ['database_name'], # Label to distinguish metrics by database
    buckets=(.005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0, 10.0, float('inf'))
)

DB_WRITE_SUCCESS_TOTAL = Counter(
    'multidb_write_success_total',
    'Total count of successful database write operations per database.',
    ['database_name']
)

DB_WRITE_FAILURE_TOTAL = Counter(
    'multidb_write_failure_total',
    'Total count of failed database write operations per database.',
    ['database_name']
)

DB_WRITE_TIMEOUT_TOTAL = Counter(
    'multidb_write_timeout_total',
    'Total count of database write operations that timed out (simulated) per database.',
    ['database_name']
)

# --- Database Functions ---

def get_db_connection(db_config):
    """
    Establishes and returns a PostgreSQL database connection using the provided config.
    """
    db_name = db_config['dbname']
    db_user = db_config['user']
    db_password = db_config['password']
    db_host = db_config['host']
    db_port = db_config['port']
    logical_db_name = db_config['name']

    try:
        app.logger.info(f"Connecting to PostgreSQL database: {db_user}@tcp({db_host}:{db_port})/{db_name} (Logical Name: {logical_db_name})")
        conn = psycopg2.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_name,
            connect_timeout=5
        )
        return conn
    except Psycopg2OperationalError as e:
        app.logger.error(f"PostgreSQL connection failed for '{logical_db_name}' (OperationalError): {e}")
        raise
    except Exception as e:
        app.logger.error(f"Error connecting to PostgreSQL database '{logical_db_name}': {e}")
        raise


def create_table(db_config):
    """Creates the timestamps table if it's not present in the specified PostgreSQL database."""
    logical_db_name = db_config['name']
    try:
        conn = get_db_connection(db_config)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS timestamps (
                id SERIAL PRIMARY KEY,
                timestamp TEXT NOT NULL
            )
        ''')
        conn.commit()
        conn.close()
        app.logger.info(f"Database table 'timestamps' ensured to exist in PostgreSQL database '{db_config['dbname']}' (Logical Name: {logical_db_name}).")
    except Exception as e:
        app.logger.error(f"Error creating database table in PostgreSQL for '{logical_db_name}': {e}")


def write_timestamp_to_db(db_config):
    """
    Writes the current timestamp to the specified database and records Prometheus metrics.
    Includes simulated timeout and general failure scenarios.
    """
    database_name_label = db_config['name']

    with DB_WRITE_LATENCY.labels(database_name=database_name_label).time():
        try:
            # Simulate a timeout or failure occasionally for demonstration.
            # Only simulate for a database named 'db1' for consistent testing.
            if os.getenv('SIMULATE_DB_FAILURE', 'false').lower() == 'true':
            #if os.getenv('SIMULATE_DB_FAILURE', 'false').lower() == 'true' and \
               #datetime.now().second % 10 == 0 and database_name_label == "db1":
                raise Psycopg2OperationalError(f"Simulated database connection error or timeout for {database_name_label}")

            conn = get_db_connection(db_config)
            cursor = conn.cursor()
            current_time = datetime.now().isoformat()
            cursor.execute("INSERT INTO timestamps (timestamp) VALUES (%s)", (current_time,))
            conn.commit()
            conn.close()
            DB_WRITE_SUCCESS_TOTAL.labels(database_name=database_name_label).inc()
            app.logger.info(f"Timestamp '{current_time}' written successfully to '{db_config['dbname']}' (Logical Name: {database_name_label}).")

        except Psycopg2OperationalError as e:
            DB_WRITE_TIMEOUT_TOTAL.labels(database_name=database_name_label).inc()
            DB_WRITE_FAILURE_TOTAL.labels(database_name=database_name_label).inc()
            app.logger.error(f"PostgreSQL write failed for '{database_name_label}' (operational error/timeout): {e}")
        except Exception as e:
            DB_WRITE_FAILURE_TOTAL.labels(database_name=database_name_label).inc()
            app.logger.error(f"Database write failed for '{database_name_label}' (general error): {e}")
        finally:
            if 'conn' in locals() and conn:
                conn.close()


# --- Periodic Background Task ---
def periodic_db_writer():
    """
    Background thread function to periodically write timestamps to all configured databases.
    """
    while True:
        for db_config in DB_CONFIGS:
            try:
                write_timestamp_to_db(db_config)
            except Exception as e:
                app.logger.error(f"Periodic DB writer encountered an error for '{db_config['name']}': {e}. Retrying after interval.")
        time.sleep(DB_WRITE_INTERVAL_SECONDS)

# --- Flask Routes ---

@app.route('/')
def health_check():
    """Simple health check endpoint."""
    app.logger.info("Health check endpoint accessed.")
    return "Flask app is running and writing timestamps to multiple databases!", 200

@app.route('/metrics')
def metrics():
    """
    Endpoint for Prometheus to scrape metrics.
    Returns the latest metrics in Prometheus exposition format.
    """
    app.logger.debug("Metrics endpoint accessed by Prometheus.")
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# --- Application Startup ---
if __name__ == '__main__':
    app.logger.info("Starting Flask application...")
    for db_conf in DB_CONFIGS:
        create_table(db_conf)

        # Initialize metrics for each database to ensure they are always exposed, even if 0
        db_name_label = db_conf['name']
        DB_WRITE_SUCCESS_TOTAL.labels(database_name=db_name_label).inc(0)
        DB_WRITE_FAILURE_TOTAL.labels(database_name=db_name_label).inc(0)
        DB_WRITE_TIMEOUT_TOTAL.labels(database_name=db_name_label).inc(0)
        # For Histogram, we don't need to explicitly touch it with 0, as it accumulates observations.
        # Its existence is determined by its first observation.

    db_writer_thread = threading.Thread(target=periodic_db_writer, daemon=True)
    db_writer_thread.start()

    app.run(host='0.0.0.0', port=5000)
