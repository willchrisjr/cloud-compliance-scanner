import os
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Text, TIMESTAMP, MetaData
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from sqlalchemy.sql import func # for CURRENT_TIMESTAMP
from google.cloud.sql.connector import Connector, IPTypes
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

logger = logging.getLogger(__name__)

# --- Database Configuration ---
DB_USER = os.environ.get("DB_USER")
DB_PASS = os.environ.get("DB_PASS")
DB_NAME = os.environ.get("DB_NAME")
# e.g. "project:region:instance"
INSTANCE_CONNECTION_NAME = os.environ.get("INSTANCE_CONNECTION_NAME")
# Always use Public IP for local development unless explicitly configured otherwise
# In a Cloud Run/App Engine environment with VPC connector, PRIVATE might be appropriate.
IP_TYPE = IPTypes.PUBLIC

# --- SQLAlchemy Setup ---
Base = declarative_base()
engine = None
SessionLocal = None

class ComplianceFinding(Base):
    """SQLAlchemy model for the compliance_findings table."""
    __tablename__ = "compliance_findings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_timestamp = Column(TIMESTAMP(timezone=True), server_default=func.now())
    gcp_project_id = Column(Text, nullable=False)
    resource_type = Column(Text, nullable=False)
    resource_id = Column(Text, nullable=False)
    finding_description = Column(Text, nullable=False)
    status = Column(Text, default='NonCompliant', nullable=False)

    def __repr__(self):
        return f"<ComplianceFinding(id={self.id}, project='{self.gcp_project_id}', resource='{self.resource_type}:{self.resource_id}')>"

def init_connection_pool() -> None:
    """
    Initializes the database connection pool using the Cloud SQL Connector.
    """
    global engine, SessionLocal
    if engine:
        logger.info("Connection pool already initialized.")
        return

    if not all([DB_USER, DB_PASS, DB_NAME]):
        raise ValueError("Missing database configuration environment variables (DB_USER, DB_PASS, DB_NAME)")

    try:
        logger.info(f"Initializing Cloud SQL connection pool for instance '{INSTANCE_CONNECTION_NAME}' database '{DB_NAME}'")
        connector = Connector(ip_type=IP_TYPE)

        def getconn():
            conn = connector.connect(
                INSTANCE_CONNECTION_NAME, # Required if not connecting via public IP
                "pg8000",
                user=DB_USER,
                password=DB_PASS,
                db=DB_NAME,
            )
            return conn

        engine = create_engine(
            "postgresql+pg8000://", # Dialect + Driver
            creator=getconn,
            pool_size=5,
            max_overflow=2,
            pool_timeout=30, # 30 seconds
            pool_recycle=1800, # 30 minutes
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.info("Database connection pool initialized successfully.")

    except Exception as e:
        logger.error(f"Failed to initialize database connection pool: {e}", exc_info=True)
        raise # Re-raise the exception to prevent the app from starting incorrectly

def create_tables() -> None:
    """Creates the database tables if they don't exist."""
    if not engine:
        logger.error("Database engine not initialized. Call init_connection_pool() first.")
        return
    try:
        logger.info("Attempting to create database tables...")
        Base.metadata.create_all(bind=engine)
        logger.info("Tables checked/created successfully.")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}", exc_info=True)

# --- Database Operations ---

def get_db() -> Session:
    """Dependency to get a database session."""
    if not SessionLocal:
        raise RuntimeError("Database not initialized. Call init_connection_pool() first.")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def add_findings(db: Session, findings: List[Dict[str, Any]]) -> None:
    """
    Adds a list of findings to the database.

    Args:
        db: The SQLAlchemy Session.
        findings: A list of dictionaries, where each dictionary represents a finding
                  and matches the ComplianceFinding model attributes.
    """
    if not findings:
        logger.info("No findings provided to add.")
        return

    try:
        db_findings = [ComplianceFinding(**finding) for finding in findings]
        db.add_all(db_findings)
        db.commit()
        logger.info(f"Successfully added {len(db_findings)} findings to the database.")
    except Exception as e:
        logger.error(f"Error adding findings to database: {e}", exc_info=True)
        db.rollback() # Rollback in case of error
        raise # Re-raise after logging and rollback

def get_findings(db: Session, project_id: Optional[str] = None) -> List[ComplianceFinding]:
    """
    Retrieves compliance findings from the database.

    Args:
        db: The SQLAlchemy Session.
        project_id: Optional GCP project ID to filter findings.

    Returns:
        A list of ComplianceFinding objects.
    """
    try:
        query = db.query(ComplianceFinding)
        if project_id:
            query = query.filter(ComplianceFinding.gcp_project_id == project_id)
        results = query.order_by(ComplianceFinding.scan_timestamp.desc(), ComplianceFinding.id).all()
        logger.info(f"Retrieved {len(results)} findings" + (f" for project {project_id}" if project_id else ""))
        return results
    except Exception as e:
        logger.error(f"Error retrieving findings from database: {e}", exc_info=True)
        raise # Re-raise after logging

# Example of how to initialize (will be called from main.py)
# if __name__ == "__main__":
#     print("Initializing DB for standalone execution...")
#     # Set dummy env vars if not present for local testing without .env
#     os.environ.setdefault("DB_USER", "test_user")
#     os.environ.setdefault("DB_PASS", "test_pass")
#     os.environ.setdefault("DB_NAME", "test_db")
#     # Provide a dummy instance name or rely on public IP if applicable
#     # os.environ.setdefault("INSTANCE_CONNECTION_NAME", "your-project:your-region:your-instance")
#
#     init_connection_pool()
#     create_tables()
#     print("DB Initialized.")
#
#     # Example Usage (requires a running DB or mock)
#     # with next(get_db()) as session:
#     #     test_finding = {
#     #         "gcp_project_id": "test-project-123",
#     #         "resource_type": "Bucket",
#     #         "resource_id": "my-test-bucket-public",
#     #         "finding_description": "Test finding: Bucket is public.",
#     #         "status": "NonCompliant"
#     #     }
#     #     add_findings(session, [test_finding])
#     #     all_findings = get_findings(session)
#     #     print(f"Found findings: {all_findings}")
