# GCP Compliance Scanner API Documentation

This document describes the API endpoints provided by the backend service.

## Base URL

The API is typically served at `http://localhost:8080` during local development. When deployed (e.g., to Cloud Run), the base URL will change.

## Authentication

The API endpoints themselves do not require authentication headers from the client (frontend). However, the backend service uses Application Default Credentials (ADC) configured in its environment to authenticate to Google Cloud APIs when performing scans.

## Endpoints

### 1. Trigger Scan

*   **Endpoint:** `POST /scan`
*   **Description:** Initiates a compliance scan for the specified GCP project. The backend runs the checks asynchronously and stores any findings in the database.
*   **Request Body:** JSON object
    ```json
    {
      "project_id": "your-gcp-project-id"
    }
    ```
    *   `project_id` (string, required): The ID of the GCP project to scan.
*   **Responses:**
    *   **`202 Accepted`** (Success): Indicates the scan was successfully initiated and completed (or is running).
        ```json
        {
          "status": "success",
          "message": "Scan initiated and completed for project your-gcp-project-id.",
          "findings_count": 0 
        }
        ```
        *   `status` (string): "success"
        *   `message` (string): A confirmation message.
        *   `findings_count` (integer, optional): The number of findings identified during this scan.
    *   **`422 Unprocessable Entity`**: If the request body is invalid (e.g., missing `project_id`). Response body follows FastAPI's standard validation error format.
    *   **`500 Internal Server Error`**: If an unexpected error occurs during the scan process (e.g., failure to connect to GCP APIs, database errors).
        ```json
        {
          "detail": "An error occurred during the scan for project your-gcp-project-id: <error details>"
        }
        ```

### 2. Get Findings

*   **Endpoint:** `GET /findings`
*   **Description:** Retrieves a list of all compliance findings stored in the database. Can be optionally filtered by project ID.
*   **Query Parameters:**
    *   `project_id` (string, optional): If provided, filters the results to only include findings for the specified GCP project ID.
*   **Responses:**
    *   **`200 OK`** (Success): Returns a list of finding objects. The list may be empty if no findings exist or match the filter.
        ```json
        [
          {
            "id": 1,
            "scan_timestamp": "2025-04-08T12:30:00.123456+00:00", // ISO 8601 format
            "gcp_project_id": "scanned-project-id",
            "resource_type": "Bucket",
            "resource_id": "my-public-bucket-123",
            "finding_description": "Bucket is publicly accessible via 'allUsers' or 'allAuthenticatedUsers'.",
            "status": "NonCompliant"
          },
          // ... more findings
        ]
        ```
        *   Each object in the array contains details about a specific compliance finding.
    *   **`500 Internal Server Error`**: If an error occurs while querying the database.
        ```json
        {
          "detail": "An error occurred while retrieving findings: <error details>"
        }
