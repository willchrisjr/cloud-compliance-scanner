# GCP Compliance Scanner Deployment Guide

This guide outlines the steps to deploy the backend API to Google Cloud Run and the frontend application to Firebase Hosting.

## Prerequisites

*   Completion of the [GCP Setup](#gcp-setup-one-time) steps outlined in the main `README.md`.
*   Google Cloud SDK (`gcloud`) installed and configured locally.
*   Docker installed locally ([Install Guide](https://docs.docker.com/get-docker/)).
*   Firebase CLI installed globally (`npm install -g firebase-tools`) and logged in (`firebase login`).
*   A GCP project with billing enabled, linked to Firebase (see Firebase Setup below).
*   Necessary IAM permissions for your user account to deploy to Cloud Run, manage Firebase Hosting, use Secret Manager, and set IAM policies (e.g., roles like `Cloud Run Admin`, `Firebase Hosting Admin`, `Secret Manager Admin`, `Project IAM Admin` or equivalent custom roles).

## Backend Deployment (Cloud Run)

The backend FastAPI application will be containerized using Docker and deployed as a Cloud Run service.

1.  **Create `backend/Dockerfile`:**
    Ensure the `Dockerfile` exists in the `backend` directory (as created previously). It should install `git` and use `gunicorn`.

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
    *   Ensure Artifact Registry API is enabled (`gcloud services enable artifactregistry.googleapis.com`).
    *   Create Artifact Registry repo if needed:
        ```bash
        gcloud artifacts repositories create cloud-run-source-deploy \
          --repository-format=docker \
          --location=${REGION} \
          --description="Docker repository for Cloud Run source deployments" \
          --project=${GCP_PROJECT_ID}
        ```
    *   Configure Docker authentication:
        ```bash
        gcloud auth configure-docker ${REGION}-docker.pkg.dev --project=${GCP_PROJECT_ID}
        ```
    *   Push the image:
        ```bash
        docker push ${IMAGE_TAG}
        ```

4.  **Set up Secret Manager for DB Password:**
    *   Ensure Secret Manager API is enabled (`gcloud services enable secretmanager.googleapis.com`).
    *   Create secret:
        ```bash
        gcloud secrets create db-password --replication-policy="automatic" --project=${GCP_PROJECT_ID}
        ```
    *   Add password version (replace `YOUR_DB_PASSWORD`):
        ```bash
        printf "YOUR_DB_PASSWORD" | gcloud secrets versions add db-password --data-file=- --project=${GCP_PROJECT_ID}
        ```

5.  **Deploy to Cloud Run:**
    *   Get instance connection name:
        ```bash
        export INSTANCE_CONNECTION_NAME=$(gcloud sql instances describe compliance-scanner-db --format='value(connectionName)' --project=${GCP_PROJECT_ID})
        ```
    *   Deploy the service:
        ```bash
        gcloud run deploy ${IMAGE_NAME} \
          --image=${IMAGE_TAG} \
          --platform=managed \
          --region=${REGION} \
          --allow-unauthenticated `# REMOVE for production/authenticated access` \
          --add-cloudsql-instances=${INSTANCE_CONNECTION_NAME} \
          --set-env-vars="DB_USER=scanner_user,DB_NAME=compliance_data,INSTANCE_CONNECTION_NAME=${INSTANCE_CONNECTION_NAME}" \
          --set-secrets="DB_PASS=db-password:latest" \
          --project=${GCP_PROJECT_ID}
        ```
    *   **Grant Secret Access:** If deployment fails with permission errors, grant the Cloud Run service account (identified in the error message, e.g., `PROJECT_NUMBER-compute@...`) the `roles/secretmanager.secretAccessor` role on the secret:
        ```bash
        gcloud secrets add-iam-policy-binding db-password \
          --member="serviceAccount:YOUR_RUN_SERVICE_ACCOUNT_EMAIL" \
          --role="roles/secretmanager.secretAccessor" \
          --project=${GCP_PROJECT_ID}
        # Then retry the deploy command.
        ```
    *   **Grant Cloud SQL Access:** Ensure the Cloud Run service account also has `roles/cloudsql.client`:
         ```bash
        gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} \
          --member="serviceAccount:YOUR_RUN_SERVICE_ACCOUNT_EMAIL" \
          --role="roles/cloudsql.client"
         ```
    *   **Note the final Service URL** provided after successful deployment (e.g., `https://gcp-compliance-scanner-backend-....a.run.app`). This is needed for the frontend configuration.

## Frontend Deployment (Firebase Hosting)

This method hosts the static React build files using Firebase Hosting's CDN and automatic SSL.

1.  **Link GCP Project to Firebase:**
    *   If you haven't already, link your GCP project to Firebase either via the [Firebase Console](https://console.firebase.google.com/) ("Add project" > Import existing GCP project) or using the CLI:
        ```bash
        firebase projects:addfirebase YOUR_GCP_PROJECT_ID
        ```

2.  **Initialize Firebase Hosting:**
    *   Navigate to the `frontend` directory.
    *   Run `firebase init hosting`.
    *   Follow prompts:
        *   Select "Use an existing project" -> Choose your project.
        *   Public directory: `dist`
        *   Configure as SPA: `Yes`
        *   Set up GitHub deploys: `No`
        *   Overwrite `dist/index.html`: `No` (if it exists from a previous build)
    *   This creates `firebase.json` and `.firebaserc`.

3.  **Configure Frontend API URL:**
    *   Create a file named `.env.production` in the `frontend` directory.
    *   Add the deployed Cloud Run Service URL (obtained from the backend deployment step):
        ```dotenv
        VITE_API_URL=https://your-cloud-run-service-url.a.run.app
        ```
    *   Ensure your frontend code (e.g., `src/App.tsx`) reads this variable:
        ```typescript
        const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8080';
        ```

4.  **Build the Frontend:**
    *   In the `frontend` directory, run:
        ```bash
        npm run build
        ```

5.  **Deploy to Firebase Hosting:**
    *   In the `frontend` directory, run:
        ```bash
        firebase deploy --only hosting
        ```

6.  **Access the Frontend:** Your application will be available at the **Hosting URL** provided by the deploy command (e.g., `https://your-project-id.web.app`).
