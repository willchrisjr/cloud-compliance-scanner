# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

 # Set the working directory in the container
 WORKDIR /app

 # Install system dependencies (including git)
 RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

 # Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install pip dependencies
# Copy only requirements first to leverage Docker cache
COPY requirements.txt .
# Install the Cloud SQL connector from Git first, then the rest
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir git+https://github.com/GoogleCloudPlatform/cloud-sql-python-connector.git && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose the port the app runs on
EXPOSE 8080

 # Define the command to run the application using Gunicorn (production server)
 # Cloud Run automatically sets the PORT environment variable.
 # Use shell form for CMD to ensure $PORT expansion
 CMD gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$PORT main:app
