# GCP Compliance Scanner Deployment Guide

This guide outlines the steps to deploy the backend API to Google Cloud Run and the frontend application to Google Cloud Storage.

## Prerequisites

*   Completion of the [GCP Setup](#gcp-setup-one-time) steps outlined in the main `README.md`.
*   Google Cloud SDK (`gcloud`) installed and configured locally.
*   Docker installed locally ([Install Guide](https://docs.docker.com/get-docker/)).
*   A GCP project with billing enabled.
*   Necessary IAM permissions for your user account to deploy to Cloud Run, manage Cloud Storage, and set IAM policies (e.g., roles like `Cloud Run Admin`, `Storage Admin`, `Project IAM Admin` or equivalent custom roles).

## Backend Deployment (Cloud Run)

The backend FastAPI application will be containerized using Docker and deployed as a Cloud Run service.

1.  **Create `backend/Dockerfile`:**
    Create a file named `Dockerfile` inside the `backend` directory with the following content:

    ```Dockerfile
    # Use an official Python runtime as a parent image
    FROM python:3.11-slim

    # Set environment variables
    ENV PYTHONDONTWRITEBYTECODE 1
    ENV PYTHONUNBUFFERED 1

    # Set the working directory in the container
    WORKDIR /app

    # Install system dependencies if needed (e.g., for specific libraries)
    # RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

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
    CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-b", ":$PORT", "main:app"]
    ```
    *Note: This Dockerfile uses Gunicorn as the production server, which is recommended for Cloud Run.*
    *You might need to add `gunicorn` to your `backend/requirements.txt` if it's not already included via `uvicorn[standard]`.*

2.  **Build the Docker Image:**
    Navigate to the `backend` directory in your terminal and run:
    ```bash
    # Replace YOUR_GCP_PROJECT_ID and choose a region like 'us-central1'
    export GCP_PROJECT_ID=YOUR_GCP_PROJECT_ID
    export REGION=us-central1
    export IMAGE_NAME=gcp-compliance-scanner-backend
    export IMAGE_TAG=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run-source-deploy/${IMAGE_NAME}

    docker build -t ${IMAGE_TAG} .
    ```

3.  **Push the Image to Artifact Registry:**
    *   Enable Artifact Registry API if not already enabled:
        ```bash
        gcloud services enable artifactregistry.googleapis.com
        ```
    *   Create a Docker repository in Artifact Registry (if you don't have one):
        ```bash
        gcloud artifacts repositories create cloud-run-source-deploy \
          --repository-format=docker \
          --location=${REGION} \
          --description="Docker repository for Cloud Run source deployments"
        ```
    *   Configure Docker to authenticate with Artifact Registry:
        ```bash
        gcloud auth configure-docker ${REGION}-docker.pkg.dev
        ```
    *   Push the image:
        ```bash
        docker push ${IMAGE_TAG}
        ```

4.  **Deploy to Cloud Run:**
    *   Run the deployment command. This connects the service to your Cloud SQL instance.
    ```bash
    # Get your Cloud SQL instance connection name again if needed
    export INSTANCE_CONNECTION_NAME=$(gcloud sql instances describe compliance-scanner-db --format='value(connectionName)')

    gcloud run deploy ${IMAGE_NAME} \
      --image=${IMAGE_TAG} \
      --platform=managed \
      --region=${REGION} \
      --allow-unauthenticated \
      --add-cloudsql-instances=${INSTANCE_CONNECTION_NAME} \
      --set-env-vars="DB_USER=scanner_user" \
      --set-env-vars="DB_NAME=compliance_data" \
      --set-env-vars="INSTANCE_CONNECTION_NAME=${INSTANCE_CONNECTION_NAME}" \
      # For the password, use Secret Manager for security:
      # 1. Create secret: gcloud secrets create db-password --replication-policy="automatic"
      # 2. Add version: printf "YOUR_DB_PASSWORD" | gcloud secrets versions add db-password --data-file=-
      # 3. Grant access to Cloud Run service account (find it via `gcloud run services describe ... --format='value(status.latestCreatedRevision.serviceAccountEmail)'`)
      #    gcloud secrets add-iam-policy-binding db-password --member="serviceAccount:YOUR_RUN_SA_EMAIL" --role="roles/secretmanager.secretAccessor"
      --set-secrets="DB_PASS=db-password:latest"
    ```
    *   `--allow-unauthenticated`: Makes the API publicly accessible. Remove this if you want to add IAM authentication later.
    *   `--add-cloudsql-instances`: Connects Cloud Run to your SQL instance via the socket.
    *   `--set-env-vars`/`--set-secrets`: Sets the necessary environment variables for the database connection. **Using Secret Manager for the password is strongly recommended.**

5.  **Update Frontend API URL:** Once deployed, Cloud Run will provide a service URL. Update the `API_URL` variable in your frontend code (e.g., in `frontend/src/App.tsx` or via environment variables during the frontend build process) to point to this new URL before deploying the frontend.

## Frontend Deployment (Cloud Storage)

This method hosts the static React build files on a Cloud Storage bucket configured for website hosting.

1.  **Build the Frontend:**
    *   Navigate to the `frontend` directory.
    *   **(Important)** Ensure the `API_URL` in your code points to your deployed Cloud Run service URL. You might use environment variables for this (e.g., `.env.production` file and Vite's env handling).
    *   Run the build command:
        ```bash
        npm run build
        ```
    *   This creates a `dist` directory containing the static HTML, CSS, and JavaScript files.

2.  **Create a Cloud Storage Bucket:**
    *   Choose a globally unique bucket name (often related to your domain name if you have one).
    ```bash
    # Replace YOUR_UNIQUE_BUCKET_NAME
    export BUCKET_NAME=YOUR_UNIQUE_BUCKET_NAME
    gsutil mb -p ${GCP_PROJECT_ID} -l ${REGION} gs://${BUCKET_NAME}
    ```

3.  **Configure Bucket for Website Hosting:**
    ```bash
    gsutil web set -m index.html -e index.html gs://${BUCKET_NAME}
    ```
    *   `-m index.html`: Sets the main page.
    *   `-e index.html`: Sets the error page (often the same for SPAs).

4.  **Upload Build Files:**
    ```bash
    gsutil -m rsync -r frontend/dist gs://${BUCKET_NAME}
    ```
    *   `-m`: Performs parallel uploads.
    *   `rsync`: Synchronizes the contents, only uploading changed files.
    *   `-r`: Recursive copy.

5.  **Make Bucket Publicly Readable:**
    ```bash
    gsutil iam ch allUsers:objectViewer gs://${BUCKET_NAME}
    ```

6.  **Access the Frontend:** Your application should be available at `http://storage.googleapis.com/${BUCKET_NAME}/` or `https://${BUCKET_NAME}.storage.googleapis.com/`. You can also configure a custom domain.

*(Alternative: Firebase Hosting provides a simpler deployment experience for static sites and SPAs, including easy custom domains and SSL.)*
