# Use a lightweight Python base image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
# This step is optimized for Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container
COPY app.py .

# Expose the port your Flask app listens on
EXPOSE 8080

# Command to run the application
# Use gunicorn for production-ready WSGI server
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
