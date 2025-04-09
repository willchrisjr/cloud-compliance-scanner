import logging
import os
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field # For request/response models
from sqlalchemy.orm import Session

# Import database functions and models
from database import (
    init_connection_pool,
    create_tables,
    get_db,
    add_findings,
    get_findings as db_get_findings, # Rename to avoid conflict
    ComplianceFinding as DBComplianceFinding # Model from DB
)

# Import scanner functions
from scanner.checks import (
    check_public_buckets,
    check_firewall_rules,
    check_iam_bindings,
    check_default_sa_usage,
    check_unused_resources,
    check_bucket_logging
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FastAPI App Setup ---
app = FastAPI(
    title="GCP Compliance Scanner API",
    description="API to trigger GCP compliance scans and retrieve findings.",
    version="0.1.0",
)

# --- CORS Configuration ---
# Allow requests from typical frontend development ports and potentially deployed frontend URL
# In production, restrict this to the actual frontend origin
origins = [
    "http://localhost",
    "http://localhost:3000", # Common React dev port
    "http://localhost:5173", # Common Vite dev port
    "https://gcp-compliance-scanner-456210.web.app" # Deployed Firebase frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- Pydantic Models ---
class ScanRequest(BaseModel):
    project_id: str = Field(..., description="The GCP Project ID to scan.")
    checks_to_run: Optional[List[str]] = Field(None, description="List of specific checks to run, e.g., ['public_buckets', 'firewall_rules']. If None or empty, run all.")

class ScanResponse(BaseModel):
    status: str
    message: str
    findings_count: Optional[int] = None

# Define a Pydantic model for the response to ensure consistency and validation
class FindingResponse(BaseModel):
    id: int
    scan_timestamp: str # Use string for simplicity in JSON
    gcp_project_id: str
    resource_type: str
    resource_id: str
    finding_description: str
    status: str

    class Config:
        orm_mode = True # Enable ORM mode to work with SQLAlchemy models

# --- Event Handlers ---
@app.on_event("startup")
async def startup_event():
    """Initialize database connection pool and create tables on startup."""
    logger.info("Application startup: Initializing database...")
    try:
        init_connection_pool()
        # It's often better to manage table creation/migrations outside the app startup
        # but for simplicity, we'll create them here if they don't exist.
        create_tables()
        logger.info("Database initialization complete.")
    except Exception as e:
        logger.critical(f"FATAL: Database initialization failed: {e}", exc_info=True)
        # Depending on the deployment, you might want to exit or prevent startup
        # For Cloud Run, it might keep restarting. Logging the critical error is key.
        # raise # Re-raising might stop FastAPI startup cleanly

@app.on_event("shutdown")
async def shutdown_event():
    """Perform cleanup on shutdown (e.g., close DB connections if needed)."""
    # The Cloud SQL connector manages the pool, explicit closing might not be needed
    # unless specific resources were acquired.
    logger.info("Application shutdown.")

# --- API Endpoints ---
@app.post("/scan", response_model=ScanResponse, status_code=status.HTTP_202_ACCEPTED)
async def trigger_scan(
    scan_request: ScanRequest,
    db: Session = Depends(get_db)
):
    """
    Triggers compliance scans for the specified GCP project and stores findings.
    """
    project_id = scan_request.project_id
    logger.info(f"Received scan request for project: {project_id}")
    all_findings = []
    checks_requested = scan_request.checks_to_run or [] # Default to empty list if None
    run_all = not checks_requested or "all" in checks_requested

    # Map check names to functions
    check_functions = {
        "public_buckets": check_public_buckets,
        "firewall_rules": check_firewall_rules,
        "iam_bindings": check_iam_bindings,
        "default_sa_usage": check_default_sa_usage,
        "unused_resources": check_unused_resources,
        "bucket_logging": check_bucket_logging,
    }

    try:
        # Run requested checks (or all)
        for check_name, check_func in check_functions.items():
            if run_all or check_name in checks_requested:
                logger.info(f"[{project_id}] Running check: {check_name}...")
                try:
                    findings = check_func(project_id)
                    all_findings.extend(findings)
                    logger.info(f"[{project_id}] Check '{check_name}' completed, found {len(findings)} findings.")
                except Exception as check_err:
                    # Log error for individual check but continue with others
                    logger.error(f"[{project_id}] Error during check '{check_name}': {check_err}", exc_info=True)
            else:
                 logger.info(f"[{project_id}] Skipping check: {check_name} (not requested).")


        logger.info(f"[{project_id}] Scan completed. Found {len(all_findings)} total potential findings.")

        # Store findings in the database
        if all_findings:
            logger.info(f"[{project_id}] Storing {len(all_findings)} findings in the database...")
            add_findings(db, all_findings)
            logger.info(f"[{project_id}] Findings stored successfully.")
        else:
            logger.info(f"[{project_id}] No findings to store.")

        return ScanResponse(
            status="success",
            message=f"Scan initiated and completed for project {project_id}.",
            findings_count=len(all_findings)
        )

    except Exception as e:
        logger.error(f"Error during scan for project {project_id}: {e}", exc_info=True)
        # Raise HTTPException to return a proper error response to the client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred during the scan for project {project_id}: {str(e)}"
        )

@app.get("/findings", response_model=List[FindingResponse])
async def get_all_findings(
    project_id: Optional[str] = None, # Optional query parameter
    db: Session = Depends(get_db)
):
    """
    Retrieves all compliance findings, optionally filtered by project ID.
    """
    logger.info(f"Received request for findings" + (f" for project: {project_id}" if project_id else ""))
    try:
        findings_db = db_get_findings(db, project_id=project_id)
        # Convert SQLAlchemy models to Pydantic models for response
        # Handle potential timezone issues if needed when converting timestamp
        response_findings = [
            FindingResponse(
                id=f.id,
                scan_timestamp=f.scan_timestamp.isoformat() if f.scan_timestamp else None,
                gcp_project_id=f.gcp_project_id,
                resource_type=f.resource_type,
                resource_id=f.resource_id,
                finding_description=f.finding_description,
                status=f.status
            ) for f in findings_db
        ]
        logger.info(f"Returning {len(response_findings)} findings.")
        return response_findings
    except Exception as e:
        logger.error(f"Error retrieving findings: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while retrieving findings: {str(e)}"
        )

# --- Root Endpoint (Optional) ---
@app.get("/")
async def root():
    """Root endpoint providing basic API information."""
    return {"message": "Welcome to the GCP Compliance Scanner API"}

# --- Run with Uvicorn (for local development) ---
# You would typically run this using: uvicorn main:app --reload --port 8080
# The Dockerfile for Cloud Run will use a production-grade server like gunicorn with uvicorn workers.
if __name__ == "__main__":
    import uvicorn
    # Ensure environment variables are loaded if running directly
    from dotenv import load_dotenv
    load_dotenv()
    # Set default port for Cloud Run compatibility if PORT env var is present
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Uvicorn server on port {port}...")
    # Note: DB initialization happens via the 'startup' event handler
    uvicorn.run(app, host="0.0.0.0", port=port)
