import os
import time
import threading
from datetime import datetime
from flask import Flask, jsonify, render_template_string
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, DBAPIError

# Prometheus metrics
from prometheus_client import Gauge, Counter, generate_latest, Histogram
import prometheus_client.metrics_core # for Flask middleware if needed later
import logging # For better logging

app = Flask(__name__)

# Basic Flask logging configuration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
app.logger.setLevel(logging.INFO)

# Database connection details from environment variables
DB_USER = os.getenv('DB_USER', 'user')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'password')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'mydatabase')

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = None  # Initialize engine to None

# --- Prometheus Metrics Definitions ---

# Gauge for database engine status (0 = not initialized, 1 = initialized)
DB_ENGINE_STATUS = Gauge('flask_db_engine_status', 'Status of the database engine (1=initialized, 0=not initialized)')

# Counters for connection and write attempts
DB_CONNECT_ATTEMPTS_TOTAL = Counter('flask_db_connect_attempts_total', 'Total database connection attempts', ['status', 'is_timeout'])
DB_WRITE_ATTEMPTS_TOTAL = Counter('flask_db_write_attempts_total', 'Total database write attempts', ['status', 'is_timeout'])

# Gauges for the last successful/failed latency (in milliseconds)
DB_CONNECT_LATENCY_MS = Gauge('flask_db_connect_latency_ms_last', 'Last database connection latency in milliseconds', ['status'])
DB_WRITE_LATENCY_MS = Gauge('flask_db_write_latency_ms_last', 'Last database write latency in milliseconds', ['status'])

# Histogram for distribution of latencies
DB_CONNECT_LATENCY_HISTOGRAM = Histogram('flask_db_connect_latency_ms', 'Database connection latency histogram in ms', buckets=[1, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000])
DB_WRITE_LATENCY_HISTOGRAM = Histogram('flask_db_write_latency_ms', 'Database write latency histogram in ms', buckets=[1, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000])


# --- End Prometheus Metrics Definitions ---


def init_db_engine():
    """Initializes the database engine."""
    global engine
    retries = 5
    DB_ENGINE_STATUS.set(0) # Assume not initialized initially
    while retries > 0:
        start_time = time.perf_counter()
        error_type = "unknown" # Default error type
        try:
            app.logger.info(f"Attempting to connect to database at {DB_HOST}:{DB_PORT}/{DB_NAME}...")
            temp_engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args={"connect_timeout": 10})
            with temp_engine.connect() as connection:
                connection.execute(text("SELECT 1")) # Test the connection
            engine = temp_engine # Assign only if successful
            latency_ms = (time.perf_counter() - start_time) * 1000
            DB_ENGINE_STATUS.set(1)
            DB_CONNECT_ATTEMPTS_TOTAL.labels(status='success', is_timeout='false').inc()
            DB_CONNECT_LATENCY_MS.labels(status='success').set(latency_ms)
            DB_CONNECT_LATENCY_HISTOGRAM.observe(latency_ms)
            app.logger.info("Database connection established successfully.")
            break
        except (SQLAlchemyError, DBAPIError) as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            is_timeout_error = "timed out" in str(e).lower() or "connection refused" in str(e).lower()
            timeout_label = 'true' if is_timeout_error else 'false'

            DB_CONNECT_ATTEMPTS_TOTAL.labels(status='failure', is_timeout=timeout_label).inc()
            DB_CONNECT_LATENCY_MS.labels(status='failure').set(latency_ms)
            DB_CONNECT_LATENCY_HISTOGRAM.observe(latency_ms) # Even failed attempts have latency
            
            app.logger.error(f"Error connecting to database: {e}")
            retries -= 1
            if retries > 0:
                app.logger.info(f"Retrying database connection in 5 seconds... ({retries} attempts left)")
                time.sleep(5)
            else:
                app.logger.error("Failed to connect to database after multiple retries. Engine will remain None.")
                engine = None # Ensure engine is None if all retries fail
                DB_ENGINE_STATUS.set(0)
                break
        except Exception as e: # Catch any other unexpected errors
            latency_ms = (time.perf_counter() - start_time) * 1000
            DB_CONNECT_ATTEMPTS_TOTAL.labels(status='failure', is_timeout='false').inc() # Treat as non-timeout failure
            DB_CONNECT_LATENCY_MS.labels(status='failure').set(latency_ms)
            DB_CONNECT_LATENCY_HISTOGRAM.observe(latency_ms)
            app.logger.error(f"An unexpected error occurred during DB initialization: {e}")
            retries -= 1
            time.sleep(5)

def write_timestamp_to_db():
    """Continuously writes the current timestamp to the database."""
    while True:
        if engine is None:
            app.logger.error("Database engine not initialized. Cannot write timestamp. Attempting to re-initialize.")
            init_db_engine() # Try to re-initialize
            if engine is None: # If re-initialization also failed
                time.sleep(5) # Wait before trying again
                continue

        start_time = time.perf_counter()
        try:
            with engine.connect() as connection:
                connection.execute(text("CREATE TABLE IF NOT EXISTS timestamps (id SERIAL PRIMARY KEY, recorded_at TIMESTAMP NOT NULL);"))
                connection.execute(text("INSERT INTO timestamps (recorded_at) VALUES (:timestamp);"), {"timestamp": datetime.now()})
                connection.commit()
            latency_ms = (time.perf_counter() - start_time) * 1000
            DB_WRITE_ATTEMPTS_TOTAL.labels(status='success', is_timeout='false').inc()
            DB_WRITE_LATENCY_MS.labels(status='success').set(latency_ms)
            DB_WRITE_LATENCY_HISTOGRAM.observe(latency_ms)
            app.logger.info(f"Timestamp recorded: {datetime.now()}")
        except (SQLAlchemyError, DBAPIError) as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            is_timeout_error = "timed out" in str(e).lower() or "connection refused" in str(e).lower()
            timeout_label = 'true' if is_timeout_error else 'false'

            DB_WRITE_ATTEMPTS_TOTAL.labels(status='failure', is_timeout=timeout_label).inc()
            DB_WRITE_LATENCY_MS.labels(status='failure').set(latency_ms)
            DB_WRITE_LATENCY_HISTOGRAM.observe(latency_ms)
            app.logger.error(f"Error writing timestamp to database: {e}")
            # Re-initialize engine on error, as connection might be stale
            init_db_engine()
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000
            DB_WRITE_ATTEMPTS_TOTAL.labels(status='failure', is_timeout='false').inc()
            DB_WRITE_LATENCY_MS.labels(status='failure').set(latency_ms)
            DB_WRITE_LATENCY_HISTOGRAM.observe(latency_ms)
            app.logger.error(f"An unexpected error occurred during DB write: {e}")
            init_db_engine()
        finally:
            time.sleep(2) # Wait for 2 seconds before the next write

@app.route('/')
def index():
    return "Flask app is running and attempting to write timestamps to PostgreSQL. Check /metrics for Prometheus data."

@app.route('/health')
def health_check():
    """Simple health check endpoint."""
    if engine:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return jsonify({"status": "healthy", "database_connection": "successful"}), 200
        except SQLAlchemyError as e:
            return jsonify({"status": "unhealthy", "database_connection": f"failed: {e}"}), 500
    return jsonify({"status": "unhealthy", "database_connection": "engine not initialized"}), 500

@app.route('/metrics')
def metrics():
    """Exposes Prometheus metrics."""
    # Ensure this endpoint doesn't block the background thread
    return generate_latest(), 200, {'Content-Type': prometheus_client.CONTENT_TYPE_LATEST}


# The /stats endpoint is now deprecated in favor of /metrics for machine consumption
# You could keep it for debugging or remove it.
@app.route('/stats')
def stats_deprecated():
    return "Please use /metrics for machine-readable statistics for Grafana.", 404

if __name__ == '__main__':
    # Initialize DB engine before starting the background thread
    init_db_engine()
    timestamp_thread = threading.Thread(target=write_timestamp_to_db)
    timestamp_thread.daemon = True
    timestamp_thread.start()

    app.run(host='0.0.0.0', port=8080)
