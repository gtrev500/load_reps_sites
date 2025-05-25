"""District Offices extraction package."""

import os
from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy import and_

# Configuration
from district_offices.config import Config

# Core functionality
from district_offices.core.scraper import (
    extract_html,
    capture_screenshot,
)

# Processing 
from district_offices.processing.llm_processor import LLMProcessor

# New Storage - ORM models and managers
from district_offices.storage.sqlite_db import SQLiteDatabase
from district_offices.storage.postgres_sync import PostgreSQLSyncManager
from district_offices.storage.models import (
    Member,
    MemberContact,
    Extraction,
    ExtractedOffice,
    ValidatedOffice,
    Artifact,
    ProvenanceLog,
    CacheEntry,
)

# Validation
from district_offices.validation.interface import ValidationInterface

# Utils
from district_offices.utils.logging import ProvenanceTracker
from district_offices.utils.html import clean_html

__version__ = "0.1.0"

# --- Backward Compatibility Wrappers ---
# These provide the same interface as the old database.py functions
# but use the new SQLite-based storage system

# Create a shared SQLite database instance
_sqlite_db: Optional[SQLiteDatabase] = None

def _get_sqlite_db() -> SQLiteDatabase:
    """Get or create the shared SQLite database instance."""
    global _sqlite_db
    if _sqlite_db is None:
        db_path = Config.get_sqlite_db_path()
        _sqlite_db = SQLiteDatabase(str(db_path))
    return _sqlite_db


def get_contact_page_url(bioguide_id: str, database_uri: str) -> Optional[str]:
    """Get contact page URL for a bioguide ID."""
    db = _get_sqlite_db()
    with db.get_session() as session:
        contact = session.query(MemberContact).filter_by(
            bioguideid=bioguide_id
        ).first()
        return contact.contact_page if contact else None

def get_bioguides_without_district_offices(database_uri: str) -> List[str]:
    """Get list of bioguide IDs without district offices."""
    # First sync from upstream if needed
    sync_manager = PostgreSQLSyncManager(database_uri, _get_sqlite_db())
    sync_manager.sync_members_from_upstream()
    sync_manager.sync_contacts_from_upstream()
    
    # Get members without offices
    db = _get_sqlite_db()
    with db.get_session() as session:
        members = session.query(Member).filter(
            and_(
                Member.currentmember == True,
                ~Member.validated_offices.any()
            )
        ).all()
        # Extract IDs while still in session
        bioguide_ids = [m.bioguideid for m in members]
    return bioguide_ids

def store_district_office(office_data: Dict[str, Any], database_uri: str) -> bool:
    """Store validated district office data."""
    db = _get_sqlite_db()
    try:
        office_id = office_data.get('office_id', f"{office_data['bioguide_id']}-{office_data.get('city', 'unknown')}")
        
        with db.get_session() as session:
            # Check if office already exists
            existing_office = session.query(ValidatedOffice).filter_by(office_id=office_id).first()
            
            if existing_office:
                # Update existing office
                existing_office.bioguide_id = office_data['bioguide_id']
                existing_office.address = office_data.get('address')
                existing_office.suite = office_data.get('suite')
                existing_office.building = office_data.get('building')
                existing_office.city = office_data.get('city')
                existing_office.state = office_data.get('state')
                existing_office.zip = office_data.get('zip')
                existing_office.phone = office_data.get('phone')
                existing_office.fax = office_data.get('fax')
                existing_office.hours = office_data.get('hours')
                existing_office.validated_at = datetime.utcnow()
                existing_office.synced_to_upstream = False
                existing_office.synced_at = None
            else:
                # Create new validated office
                validated_office = ValidatedOffice(
                    office_id=office_id,
                    bioguide_id=office_data['bioguide_id'],
                    address=office_data.get('address'),
                    suite=office_data.get('suite'),
                    building=office_data.get('building'),
                    city=office_data.get('city'),
                    state=office_data.get('state'),
                    zip=office_data.get('zip'),
                    phone=office_data.get('phone'),
                    fax=office_data.get('fax'),
                    hours=office_data.get('hours')
                )
                session.add(validated_office)
            
            session.commit()
        
        # Don't export immediately - let the caller handle batch exports
        return True
    except Exception as e:
        print(f"Error storing district office: {e}")
        return False

def check_district_office_exists(bioguide_id: str, database_uri: str) -> bool:
    """Check if district office exists for a bioguide ID."""
    db = _get_sqlite_db()
    offices = db.get_validated_offices_for_member(bioguide_id)
    return len(offices) > 0

# === Staging Compatibility Layer ===
# These classes provide backward compatibility for the validation runner
# while the underlying storage has migrated to SQLite. They wrap SQLite
# operations to maintain the existing validation interface.

class ExtractionStatus(Enum):
    """Status of an extraction (compatibility wrapper for validation runner)."""
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    FAILED = "failed"

@dataclass
class ExtractionData:
    """Legacy extraction data structure (compatibility wrapper for validation runner).
    
    This wraps SQLite data to maintain backward compatibility with validation/runner.py."""
    bioguide_id: str
    status: ExtractionStatus
    extraction_timestamp: int
    validation_timestamp: Optional[int] = None
    source_url: Optional[str] = None
    extracted_offices: List[Dict[str, Any]] = None
    artifacts: Dict[str, str] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.extracted_offices is None:
            self.extracted_offices = []
        if self.artifacts is None:
            self.artifacts = {}

class StagingManager:
    """Compatibility wrapper that provides the legacy staging interface backed by SQLite.
    
    This class maintains the same interface as the old filesystem-based staging system
    but uses SQLite for all storage operations. It's used by validation/runner.py to
    maintain backward compatibility while the underlying storage has been modernized.
    
    TODO: Consider refactoring validation/runner.py to use SQLiteDatabase directly.
    """
    
    def __init__(self, staging_dir: Optional[str] = None):
        """Initialize staging manager with SQLite backend.
        
        Args:
            staging_dir: Ignored - no longer used with SQLite storage
        """
        self.db = _get_sqlite_db()
    
    def get_extraction_data(self, bioguide_id: str) -> Optional[ExtractionData]:
        """Get extraction data for a bioguide ID."""
        with self.db.get_session() as session:
            extraction = session.query(Extraction).filter(
                Extraction.bioguide_id == bioguide_id
            ).order_by(
                Extraction.created_at.desc()
            ).first()
            
            if not extraction:
                return None
            
            # Convert to legacy format while in session
            artifacts = {}
            for artifact in extraction.artifacts:
                if artifact.artifact_type == "html":
                    artifacts["html_content"] = f"artifact:{artifact.id}"
                elif artifact.artifact_type == "contact_sections":
                    artifacts["contact_sections"] = f"artifact:{artifact.id}"
            
            offices = []
            for office in extraction.offices:
                offices.append({
                    "address": office.address,
                    "suite": office.suite,
                    "building": office.building,
                    "city": office.city,
                    "state": office.state,
                    "zip": office.zip,
                    "phone": office.phone,
                    "fax": office.fax,
                    "hours": office.hours
                })
            
            # Extract all data while in session
            return ExtractionData(
                bioguide_id=extraction.bioguide_id,
                status=ExtractionStatus(extraction.status),
                extraction_timestamp=extraction.extraction_timestamp,
                validation_timestamp=extraction.validation_timestamp,
                source_url=extraction.source_url,
                extracted_offices=offices,
                artifacts=artifacts,
                error_message=extraction.error_message
            )
    
    def load_pending_extractions(self) -> List[str]:
        """Get list of pending extractions."""
        with self.db.get_session() as session:
            extractions = session.query(Extraction).filter_by(status='pending').all()
            # Extract bioguide_ids while still in session
            return [e.bioguide_id for e in extractions]
    
    def load_all_extractions(self) -> List[str]:
        """Get list of all extractions."""
        with self.db.get_session() as session:
            extractions = session.query(Extraction).all()
            return [e.bioguide_id for e in extractions]
    
    def mark_validated(self, extraction_id: int, is_valid: bool) -> bool:
        """Mark extraction as validated or rejected.
        
        Args:
            extraction_id: Specific extraction ID to update
            is_valid: Whether the extraction was validated (True) or rejected (False)
            
        Returns:
            bool: True if status was updated successfully
        """
        status = 'validated' if is_valid else 'rejected'
        return self.db.update_extraction_status(extraction_id, status)
    
    def get_staging_summary(self) -> Dict[str, int]:
        """Get summary of staging status."""
        with self.db.get_session() as session:
            pending = session.query(Extraction).filter_by(status='pending').count()
            validated = session.query(Extraction).filter_by(status='validated').count()
            rejected = session.query(Extraction).filter_by(status='rejected').count()
            failed = session.query(Extraction).filter_by(status='failed').count()
            
            return {
                'pending': pending,
                'validated': validated,
                'rejected': rejected,
                'failed': failed,
                'total': pending + validated + rejected + failed
            }

__all__ = [
    # Configuration
    "Config",
    # Core
    "extract_html",
    "capture_screenshot", 
    # Utils
    "clean_html",
    # Processing
    "LLMProcessor",
    # New Storage
    "SQLiteDatabase",
    "PostgreSQLSyncManager",
    "Member",
    "MemberContact",
    "Extraction",
    "ExtractedOffice",
    "ValidatedOffice",
    "Artifact",
    "ProvenanceLog",
    "CacheEntry",
    # Legacy Storage (backward compatibility)
    "get_db_connection",
    "get_contact_page_url",
    "get_bioguides_without_district_offices",
    "store_district_office",
    "check_district_office_exists",
    "StagingManager",
    "ExtractionStatus",
    "ExtractionData",
    # Validation
    "ValidationInterface",
    # Utils
    "ProvenanceTracker",
]