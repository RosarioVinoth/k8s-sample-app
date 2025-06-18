# app.py

import os
import sqlite3
import time
import threading
from datetime import datetime

from flask import Flask, Response
from prometheus_client import Histogram, Counter, generate_latest, CONTENT_TYPE_LATEST

# --- OpenTelemetry Tracing Imports ---
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.trace import SpanKind
from opentelemetry.semconv.trace import SpanAttributes

# Initialize Flask app
app = Flask(__name__)

# --- Database Configuration ---
DB_NAME = os.getenv('DB_NAME', ':memory:')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')

try:
    DB_WRITE_INTERVAL_SECONDS = int(os.getenv('DB_WRITE_INTERVAL_SECONDS', 5))
except ValueError:
    print("Warning: DB_WRITE_INTERVAL_SECONDS environment variable is not an integer. Using default 5 seconds.")
    DB_WRITE_INTERVAL_SECONDS = 5

# --- Prometheus Metrics Initialization ---
DB_WRITE_LATENCY = Histogram(
    'db_write_latency_seconds',
    'Latency of database write operations to the timestamps table.',
    buckets=(.005, .01, .025, .05, .1, .25, .5, 1.0, 2.5, 5.0, 10.0, float('inf'))
)
DB_WRITE_SUCCESS_TOTAL = Counter(
    'db_write_success_total',
    'Total count of successful database write operations.'
)
DB_WRITE_FAILURE_TOTAL = Counter(
    'db_write_failure_total',
    'Total count of failed database write operations.'
)
DB_WRITE_TIMEOUT_TOTAL = Counter(
    'db_write_timeout_total',
    'Total count of database write operations that timed out (simulated).'
)

# --- OpenTelemetry Tracing Configuration ---
def init_tracer():
    """Initializes the OpenTelemetry tracer and OTLP exporter."""
    # Define resource attributes for your service
    resource = Resource.create({
        SpanAttributes.SERVICE_NAME: "flask-db-writer",
        SpanAttributes.SERVICE_VERSION: "1.0.0",
        "env": os.getenv("ENVIRONMENT", "development"),
    })

    # Set up the TracerProvider
    provider = TracerProvider(resource=resource)

    # Configure OTLP exporter to send traces to Tempo
    # By default, it sends to http://localhost:4317 (gRPC) or http://localhost:4318 (HTTP)
    # You'll typically use an OpenTelemetry Collector as an intermediary.
    # The URL can be set via OTEL_EXPORTER_OTLP_ENDPOINT environment variable.
    # For Tempo, the default OTLP gRPC port is 4317.
    # Example: OTEL_EXPORTER_OTLP_ENDPOINT="http://tempo-distributor.tempo.svc.cluster.local:4317"
    otlp_exporter = OTLPSpanExporter()

    # Add the exporter to the TracerProvider
    span_processor = BatchSpanProcessor(otlp_exporter)
    provider.add_span_processor(span_processor)

    # Set the global tracer provider
    trace.set_tracer_provider(provider)

    # Get a tracer for this module/application
    return trace.get_tracer(__name__)

# Initialize tracer globally
tracer = init_tracer()

# --- Database Functions ---

def get_db_connection():
    """Establishes and returns a database connection."""
    if DB_NAME == ':memory:' or not DB_NAME.endswith('.db'):
        print(f"Connecting to SQLite database: {DB_NAME}")
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
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
        #     raise
        print("WARNING: External database connection not implemented in this example.")
        print("Please replace SQLite connection with your actual database driver and connection logic.")
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        return conn


def create_table():
    """Creates the timestamps table if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
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
    Writes the current timestamp to the database, records Prometheus metrics,
    and creates an OpenTelemetry span for tracing.
    """
    # Create a new OpenTelemetry span for this database write operation
    # SpanKind.CLIENT indicates an outgoing request (e.g., to a database)
    with tracer.start_as_current_span(
        "db_write",
        kind=SpanKind.CLIENT,
        attributes={
            SpanAttributes.DB_SYSTEM: "sqlite" if DB_NAME == ':memory:' or DB_NAME.endswith('.db') else "sql",
            SpanAttributes.DB_NAME: DB_NAME,
            SpanAttributes.DB_OPERATION: "INSERT",
            SpanAttributes.DB_STATEMENT: "INSERT INTO timestamps (timestamp) VALUES (?)",
            # Add more attributes as needed, e.g., db.user, network.peer.address
        }
    ) as span:
        with DB_WRITE_LATENCY.time():
            try:
                if os.getenv('SIMULATE_DB_FAILURE', 'false').lower() == 'true' and \
                   datetime.now().second % 10 == 0:
                    span.set_status(trace.Status(trace.StatusCode.ERROR, "Simulated database connection error or timeout"))
                    span.record_exception(sqlite3.OperationalError("Simulated database connection error or timeout"))
                    raise sqlite3.OperationalError("Simulated database connection error or timeout")

                conn = get_db_connection()
                cursor = conn.cursor()
                current_time = datetime.now().isoformat()
                cursor.execute("INSERT INTO timestamps (timestamp) VALUES (?)", (current_time,))
                conn.commit()
                conn.close()
                DB_WRITE_SUCCESS_TOTAL.inc()
                print(f"Timestamp '{current_time}' written successfully to '{DB_NAME}'.")
                span.set_status(trace.Status(trace.StatusCode.OK)) # Mark span as success

            except (sqlite3.OperationalError, Exception) as e:
                DB_WRITE_FAILURE_TOTAL.inc()
                # Set span status to ERROR and record the exception
                span.set_status(trace.Status(trace.StatusCode.ERROR, f"Database write failed: {e}"))
                span.record_exception(e)
                if "timeout" in str(e).lower() or "operationalerror" in str(e).lower():
                    DB_WRITE_TIMEOUT_TOTAL.inc()
                    span.set_attribute("db.timeout", True) # Custom attribute for timeout
                    print(f"Database write failed (simulated timeout/operational error): {e}")
                else:
                    print(f"Database write failed (general error): {e}")


# --- Periodic Background Task ---
def periodic_db_writer():
    """
    Background thread function to periodically write timestamps to the database.
    Each write will now also generate an OpenTelemetry trace.
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
    create_table()

    db_writer_thread = threading.Thread(target=periodic_db_writer, daemon=True)
    db_writer_thread.start()

    app.run(host='0.0.0.0', port=5000)
