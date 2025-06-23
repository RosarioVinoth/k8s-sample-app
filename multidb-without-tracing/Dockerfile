# Use a lightweight Python base image
FROM python:3.9-slim-buster

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to take advantage of Docker layer caching
COPY requirements.txt .

# Install Python dependencies from requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY app.py .

# Expose the port that the Flask application will run on
EXPOSE 5000

# Define the command to run the Flask application using Gunicorn
# --access-logfile -: Directs Gunicorn's access logs to stdout
# --error-logfile -: Directs Gunicorn's error logs to stderr
# -w 4: Specifies 4 worker processes (adjust based on your CPU cores and application's nature)
# -b 0.0.0.0:5000: Binds Gunicorn to all network interfaces on port 5000
# app:app: Specifies the module (app.py) and the Flask application instance (app) within it
CMD ["gunicorn", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "-w", "4", \
     "-b", "0.0.0.0:5000", \
     "app:app"]

# --- How to Build and Run ---
# 1. Ensure you have 'app.py' and 'requirements.txt' in the same directory as this Dockerfile.
# 2. Build the Docker image:
#    docker build -t my-flask-multi-db-app .
# 3. Run the Docker container, providing the necessary environment variables:
#    docker run -d -p 5000:5000 \
#      --name flask-multi-db \
#      -e DATABASE_NAMES="prod,analytics" \
#      -e PROD_DB_HOST="your_prod_db_host" \
#      -e PROD_DB_PORT="5432" \
#      -e PROD_DB_USER="your_prod_user" \
#      -e PROD_DB_PASSWORD="your_prod_password" \
#      -e PROD_DB_DBNAME="your_prod_db_name" \
#      -e ANALYTICS_DB_HOST="your_analytics_db_host" \
#      -e ANALYTICS_DB_PORT="5432" \
#      -e ANALYTICS_DB_USER="your_analytics_user" \
#      -e ANALYTICS_DB_PASSWORD="your_analytics_password" \
#      -e ANALYTICS_DB_DBNAME="your_analytics_db_name" \
#      my-flask-multi-db-app

# --- Important Notes for OpenShift/Kubernetes ---
# When deploying to OpenShift/Kubernetes, you would:
# - Build your image and push it to a registry (e.g., quay.io, Docker Hub).
# - Use the provided Kubernetes Deployment and Secret/ConfigMap YAMLs
#   to inject the environment variables, rather than providing them directly
#   with `docker run -e`. This ensures secure and dynamic configuration.
