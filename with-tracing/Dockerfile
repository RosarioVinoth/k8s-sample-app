# Dockerfile

# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask application code into the container at /app
COPY app.py .

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Run the Flask app when the container starts
# Using gunicorn for production-ready deployment is recommended:
# CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
# For simplicity and direct execution in this example, we use Flask's built-in server.
CMD ["python", "app.py"]
