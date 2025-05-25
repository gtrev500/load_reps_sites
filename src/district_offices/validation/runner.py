#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from typing import List, Dict, Optional, Any

# Add parent directory to path for imports when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Import our modules
from district_offices import (
    StagingManager, 
    ExtractionStatus,
    store_district_office,
    ProvenanceTracker
)
from district_offices.validation.interface import ValidationInterface

# Import SQLite database for artifact loading
_sqlite_db = None

def _get_sqlite_db():
    """Get SQLite database instance (lazy loading)."""
    global _sqlite_db
    if _sqlite_db is None:
        from district_offices.storage.sqlite_db import SQLiteDatabase
        from district_offices.config import Config
        db_path = Config.get_sqlite_db_path()
        _sqlite_db = SQLiteDatabase(str(db_path))
    return _sqlite_db

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

def validate_from_staging(
    bioguide_id: str,
    staging_manager: StagingManager,
    database_uri: Optional[str] = None
) -> bool:
    """Validate a single extraction from staging.
    
    Args:
        bioguide_id: The bioguide ID to validate
        staging_manager: StagingManager instance
        database_uri: Database URI for storage
        
    Returns:
        True if validation was successful, False otherwise
    """
    try:
        # Get extraction data from staging
        extraction_data = staging_manager.get_extraction_data(bioguide_id)
        if not extraction_data:
            log.error(f"No extraction data found for {bioguide_id}")
            return False
        
        if extraction_data.status != ExtractionStatus.PENDING:
            log.warning(f"Extraction for {bioguide_id} is not pending (status: {extraction_data.status.value})")
            return False
        
        # Load required artifacts
        html_content = ""
        contact_sections = ""
        db = _get_sqlite_db()
        
        # Get the extraction ID
        extraction_id = None
        with db.get_session() as session:
            from district_offices.storage.models import Extraction
            extraction = session.query(Extraction).filter(
                Extraction.bioguide_id == bioguide_id
            ).order_by(
                Extraction.created_at.desc()
            ).first()
            if extraction:
                extraction_id = extraction.id
        
        # Load HTML content from artifacts
        if "html_content" in extraction_data.artifacts:
            artifact_ref = extraction_data.artifacts["html_content"]
            if artifact_ref.startswith("artifact:"):
                artifact_id = int(artifact_ref.split(":")[1])
                html_content = db.get_artifact_content(artifact_id)
                if html_content:
                    html_content = html_content.decode('utf-8')
            elif os.path.exists(artifact_ref):  # Legacy file path
                with open(artifact_ref, 'r', encoding='utf-8') as f:
                    html_content = f.read()
        
        # Load contact sections from artifacts
        if "contact_sections" in extraction_data.artifacts:
            artifact_ref = extraction_data.artifacts["contact_sections"]
            if artifact_ref.startswith("artifact:"):
                artifact_id = int(artifact_ref.split(":")[1])
                contact_sections = db.get_artifact_content(artifact_id)
                if contact_sections:
                    contact_sections = contact_sections.decode('utf-8')
            elif os.path.exists(artifact_ref):  # Legacy file path
                with open(artifact_ref, 'r', encoding='utf-8') as f:
                    contact_sections = f.read()
        
        # Initialize validation interface with browser validation as default
        validation_interface = ValidationInterface(browser_validation=True)
        
        # Perform validation
        log.info(f"Starting validation for {bioguide_id}")
        is_valid, validated_offices = validation_interface.validate_office_data(
            bioguide_id=bioguide_id,
            offices=extraction_data.extracted_offices,
            html_content=html_content,
            url=extraction_data.source_url,
            contact_sections=contact_sections,
            extraction_id=extraction_id
        )
        
        # Mark extraction as validated or rejected
        success = staging_manager.mark_validated(extraction_id, is_valid)
        if not success:
            log.error(f"Failed to mark extraction {extraction_id} as validated/rejected")
            return False
        
        # Store if validation was successful and database URI provided
        if is_valid and validated_offices and database_uri:
            log.info(f"Auto-storing validated offices for {bioguide_id}")
            store_success = False
            
            for office in validated_offices:
                # Add the bioguide_id to each office
                office_data = office.copy()
                office_data["bioguide_id"] = bioguide_id
                
                # Store in the database
                success = store_district_office(office_data, database_uri)
                store_success = store_success or success
            
            if store_success:
                log.info(f"Successfully stored district offices for {bioguide_id}")
            else:
                log.error(f"Failed to store district offices for {bioguide_id}")
                return False
        
        log.info(f"Validation completed for {bioguide_id}: {'approved' if is_valid else 'rejected'}")
        return True
        
    except Exception as e:
        log.error(f"Error validating {bioguide_id}: {e}")
        return False

def validate_all_pending(
    staging_manager: StagingManager,
    database_uri: Optional[str] = None,
    batch_size: Optional[int] = None
) -> Dict[str, Any]:
    """Validate all pending extractions.
    
    Args:
        staging_manager: StagingManager instance
        database_uri: Database URI for storage
        batch_size: Maximum number of extractions to validate in this run
        
    Returns:
        Dictionary with validation summary
    """
    pending_bioguides = staging_manager.load_pending_extractions()
    
    if not pending_bioguides:
        log.info("No pending extractions found")
        return {
            "total_pending": 0,
            "processed": 0,
            "validated": 0,
            "rejected": 0,
            "errors": 0
        }
    
    log.info(f"Found {len(pending_bioguides)} pending extractions")
    
    # Apply batch size limit if specified
    if batch_size and batch_size < len(pending_bioguides):
        pending_bioguides = pending_bioguides[:batch_size]
        log.info(f"Processing batch of {batch_size} extractions")
    
    processed = 0
    validated = 0
    rejected = 0
    errors = 0
    
    for bioguide_id in pending_bioguides:
        log.info(f"Validating extraction for {bioguide_id}")
        
        try:
            # Get extraction data to check validation result
            extraction_data_before = staging_manager.get_extraction_data(bioguide_id)
            if not extraction_data_before:
                log.error(f"Could not load extraction data for {bioguide_id}")
                errors += 1
                continue
            
            # Perform validation
            success = validate_from_staging(bioguide_id, staging_manager, database_uri)
            processed += 1
            
            if success:
                # Check final status to count validated vs rejected
                extraction_data_after = staging_manager.get_extraction_data(bioguide_id)
                if extraction_data_after:
                    if extraction_data_after.status == ExtractionStatus.VALIDATED:
                        validated += 1
                    elif extraction_data_after.status == ExtractionStatus.REJECTED:
                        rejected += 1
                else:
                    log.warning(f"Could not determine final status for {bioguide_id}")
            else:
                errors += 1
                
        except Exception as e:
            log.error(f"Error processing {bioguide_id}: {e}")
            errors += 1
    
    summary = {
        "total_pending": len(staging_manager.load_pending_extractions()) + processed,  # Original count
        "processed": processed,
        "validated": validated,
        "rejected": rejected,
        "errors": errors
    }
    
    log.info(f"Validation summary: {summary}")
    return summary


def main():
    """Main function for the validation runner."""
    parser = argparse.ArgumentParser(
        description="Validate district office extractions from staging."
    )
    parser.add_argument(
        "--bioguide-id",
        type=str,
        help="Validate a specific bioguide ID from staging"
    )
    parser.add_argument(
        "--all-pending", "--all",
        action="store_true",
        help="Validate all pending extractions"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-validate previously processed extractions"
    )
    parser.add_argument(
        "--db-uri",
        type=str,
        help="Database URI for storage (if not provided, uses DATABASE_URI environment variable)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Maximum number of extractions to validate in this run"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)
    
    # Get database URI
    database_uri = args.db_uri or os.environ.get("DATABASE_URI")
    
    # Initialize staging manager
    staging_manager = StagingManager()
    log.info(f"Staging manager initialized: {staging_manager.staging_root}")
    
    # Validate specific bioguide ID
    if args.bioguide_id:
        log.info(f"Validating bioguide ID: {args.bioguide_id}")
        
        success = validate_from_staging(
            args.bioguide_id,
            staging_manager,
            database_uri
        )
        
        if success:
            log.info(f"Successfully validated {args.bioguide_id}")
        else:
            log.error(f"Failed to validate {args.bioguide_id}")
            sys.exit(1)
    
    # Validate all pending extractions
    elif args.all_pending:
        log.info("Validating all pending extractions")
        
        summary = validate_all_pending(
            staging_manager,
            database_uri,
            args.batch_size
        )
        
        log.info(f"Validation complete: {summary}")
        
        # Print summary to stdout for easy parsing
        print(f"Processed: {summary['processed']}")
        print(f"Validated: {summary['validated']}")
        print(f"Rejected: {summary['rejected']}")
        print(f"Errors: {summary['errors']}")
    
    else:
        parser.print_help()
        sys.exit(1)
    
    # Print staging summary
    staging_summary = staging_manager.get_staging_summary()
    log.info(f"Staging summary: {staging_summary}")

if __name__ == "__main__":
    main()