#!/usr/bin/env python3

import argparse
import logging
import os
import sys
import time
import webbrowser
from typing import List, Dict, Optional, Any

# Add parent directory to path for imports when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Import our modules
from district_offices.storage import database
from district_offices.validation.interface import ValidationInterface
from district_offices.storage.staging import StagingManager, ExtractionStatus
from district_offices.utils.logging import ProvenanceTracker

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

def validate_from_staging(
    bioguide_id: str,
    staging_manager: StagingManager,
    database_uri: Optional[str] = None,
    auto_store: bool = False,
    browser_validation: bool = False
) -> bool:
    """Validate a single extraction from staging.
    
    Args:
        bioguide_id: The bioguide ID to validate
        staging_manager: StagingManager instance
        database_uri: Database URI for auto-storage
        auto_store: Whether to automatically store validated results
        browser_validation: Whether to use browser-based validation
        
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
        
        # Load HTML content
        html_path = None
        if "html_content" in extraction_data.artifacts:
            html_path = extraction_data.artifacts["html_content"]
        elif "html" in extraction_data.artifacts:
            html_path = extraction_data.artifacts["html"]
        
        if html_path and os.path.exists(html_path):
            with open(html_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
        else:
            log.warning(f"HTML content file not found: {html_path}")
        
        # Load contact sections
        if "contact_sections" in extraction_data.artifacts:
            contact_sections_path = extraction_data.artifacts["contact_sections"]
            if os.path.exists(contact_sections_path):
                with open(contact_sections_path, 'r', encoding='utf-8') as f:
                    contact_sections = f.read()
            else:
                log.warning(f"Contact sections file not found: {contact_sections_path}")
        
        # Initialize validation interface
        validation_interface = ValidationInterface(browser_validation=browser_validation)
        
        # Perform validation
        log.info(f"Starting validation for {bioguide_id}")
        is_valid, validated_offices = validation_interface.validate_office_data(
            bioguide_id=bioguide_id,
            offices=extraction_data.extracted_offices,
            html_content=html_content,
            url=extraction_data.source_url,
            contact_sections=contact_sections
        )
        
        # Mark extraction as validated or rejected
        success = staging_manager.mark_validated(bioguide_id, is_valid)
        if not success:
            log.error(f"Failed to mark {bioguide_id} as validated/rejected")
            return False
        
        # Auto-store if requested and validation was successful
        if auto_store and is_valid and validated_offices and database_uri:
            log.info(f"Auto-storing validated offices for {bioguide_id}")
            store_success = False
            
            for office in validated_offices:
                # Add the bioguide_id to each office
                office_data = office.copy()
                office_data["bioguide_id"] = bioguide_id
                
                # Store in the database
                success = database.store_district_office(office_data, database_uri)
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
    auto_store: bool = False,
    batch_size: Optional[int] = None,
    browser_validation: bool = False
) -> Dict[str, Any]:
    """Validate all pending extractions.
    
    Args:
        staging_manager: StagingManager instance
        database_uri: Database URI for auto-storage
        auto_store: Whether to automatically store validated results
        batch_size: Maximum number of extractions to validate in this run
        browser_validation: Whether to use browser-based validation
        
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
            success = validate_from_staging(bioguide_id, staging_manager, database_uri, auto_store, browser_validation)
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

def open_multiple_validation_windows(
    staging_manager: StagingManager,
    bioguide_ids: List[str],
    max_windows: int = 5,
    browser_validation: bool = False
) -> List[str]:
    """Open validation windows for multiple bioguide IDs simultaneously.
    
    This is purely cosmetic for batch review - no validation checks or storage.
    
    Args:
        staging_manager: StagingManager instance
        bioguide_ids: List of bioguide IDs to open validation for
        max_windows: Maximum number of browser windows to open at once
        browser_validation: Whether to use browser-based validation
        
    Returns:
        List of bioguide IDs that had validation windows opened successfully
    """
    validation_interface = ValidationInterface(browser_validation=browser_validation)
    opened_successfully = []
    
    # Limit the number of windows to prevent overwhelming the system
    bioguide_ids_to_process = bioguide_ids[:max_windows]
    
    if len(bioguide_ids) > max_windows:
        log.warning(f"Limiting to {max_windows} windows (requested {len(bioguide_ids)})")
    
    log.info(f"Opening validation windows for {len(bioguide_ids_to_process)} bioguide IDs (cosmetic only)")
    
    for bioguide_id in bioguide_ids_to_process:
        try:
            # Get extraction data from staging - no status validation since this is cosmetic
            extraction_data = staging_manager.get_extraction_data(bioguide_id)
            if not extraction_data:
                log.warning(f"No extraction data found for {bioguide_id}, skipping")
                continue
            
            # Load required artifacts with minimal error handling since this is cosmetic
            html_content = ""
            contact_sections = ""
            
            # Load HTML content
            html_path = None
            if "html_content" in extraction_data.artifacts:
                html_path = extraction_data.artifacts["html_content"]
            elif "html" in extraction_data.artifacts:
                html_path = extraction_data.artifacts["html"]
            
            if html_path and os.path.exists(html_path):
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            
            # Load contact sections
            if "contact_sections" in extraction_data.artifacts:
                contact_sections_path = extraction_data.artifacts["contact_sections"]
                if os.path.exists(contact_sections_path):
                    with open(contact_sections_path, 'r', encoding='utf-8') as f:
                        contact_sections = f.read()
            
            # Generate validation HTML
            validation_html_path = validation_interface.generate_validation_html(
                bioguide_id=bioguide_id,
                extracted_offices=extraction_data.extracted_offices,
                html_content=html_content,
                url=extraction_data.source_url,
                contact_sections=contact_sections
            )
            
            # Open validation interface in browser (non-blocking)
            validation_interface.open_validation_interface_nonblocking(validation_html_path)
            opened_successfully.append(bioguide_id)
            log.info(f"Opened validation window for {bioguide_id}")
            
            # Small delay between opening windows to prevent overwhelming the browser
            time.sleep(0.2)
            
        except Exception as e:
            log.warning(f"Error opening validation window for {bioguide_id}: {e}, continuing with next")
            continue
    
    log.info(f"Successfully opened {len(opened_successfully)} validation windows")
    return opened_successfully

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
        "--auto-store",
        action="store_true",
        help="Automatically store validated results in the database"
    )
    parser.add_argument(
        "--browser-validation",
        action="store_true",
        help="Use browser-based validation with Accept/Reject buttons"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-validate previously processed extractions"
    )
    parser.add_argument(
        "--staging-dir",
        type=str,
        help="Custom staging directory path"
    )
    parser.add_argument(
        "--db-uri",
        type=str,
        help="Database URI for auto-storage (if not provided, uses DATABASE_URI environment variable)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        help="Maximum number of extractions to validate in this run"
    )
    parser.add_argument(
        "--open-multiple",
        action="store_true",
        help="Open validation windows for multiple extractions (cosmetic batch review)"
    )
    parser.add_argument(
        "--no-store",
        action="store_true",
        help="Skip validation processing and storage (for data exploration only)"
    )
    parser.add_argument(
        "--max-windows",
        type=int,
        default=5,
        help="Maximum number of browser windows to open simultaneously (default: 5)"
    )
    parser.add_argument(
        "--bioguide-ids",
        type=str,
        nargs="+",
        help="Open validation windows for specific bioguide IDs (space-separated)"
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
    
    # Get database URI if auto-store is enabled
    database_uri = None
    if args.auto_store:
        database_uri = args.db_uri or os.environ.get("DATABASE_URI")
        if not database_uri:
            log.error("Database URI required for auto-store mode")
            sys.exit(1)
    
    # Initialize staging manager
    staging_manager = StagingManager(args.staging_dir)
    log.info(f"Staging manager initialized: {staging_manager.staging_root}")
    
    # Validate specific bioguide ID
    if args.bioguide_id:
        log.info(f"Validating bioguide ID: {args.bioguide_id}")
        
        success = validate_from_staging(
            args.bioguide_id,
            staging_manager,
            database_uri,
            args.auto_store,
            args.browser_validation
        )
        
        if success:
            log.info(f"Successfully validated {args.bioguide_id}")
        else:
            log.error(f"Failed to validate {args.bioguide_id}")
            sys.exit(1)
    
    # Validate all pending extractions
    elif args.all_pending and not args.open_multiple:
        log.info("Validating all pending extractions")
        
        summary = validate_all_pending(
            staging_manager,
            database_uri,
            args.auto_store,
            args.batch_size,
            args.browser_validation
        )
        
        log.info(f"Validation complete: {summary}")
        
        # Print summary to stdout for easy parsing
        print(f"Processed: {summary['processed']}")
        print(f"Validated: {summary['validated']}")
        print(f"Rejected: {summary['rejected']}")
        print(f"Errors: {summary['errors']}")
    
    # Open multiple validation windows (cosmetic only or combined with --all)
    elif args.open_multiple:
        log.info("Opening multiple validation windows (cosmetic batch review)")
        
        # Determine which bioguide IDs to open
        if args.bioguide_ids:
            # Use specific bioguide IDs provided
            bioguide_ids = args.bioguide_ids
            log.info(f"Opening validation windows for specified bioguide IDs: {bioguide_ids}")
        elif args.all_pending:
            # Use all extractions from staging when --all is specified (no status filtering for data exploration)
            all_extractions = staging_manager.load_all_extractions()
            
            if not all_extractions:
                log.info("No extractions found in staging")
                sys.exit(0)
            
            bioguide_ids = all_extractions
            log.info(f"Found {len(bioguide_ids)} extractions in staging (all statuses for data exploration)")
        else:
            # Default: use pending extractions only
            pending_bioguides = staging_manager.load_pending_extractions()
            if not pending_bioguides:
                log.info("No pending extractions found")
                sys.exit(0)
            
            bioguide_ids = pending_bioguides
            log.info(f"Found {len(bioguide_ids)} pending extractions")
        
        # Open the validation windows (up to max_windows)
        opened_successfully = open_multiple_validation_windows(
            staging_manager,
            bioguide_ids,
            args.max_windows,
            args.browser_validation
        )
        
        log.info(f"Opened validation windows for {len(opened_successfully)} bioguide IDs:")
        for bioguide_id in opened_successfully:
            print(f"  - {bioguide_id}")
        
        if len(opened_successfully) < len(bioguide_ids):
            failed_count = len(bioguide_ids) - len(opened_successfully)
            if len(bioguide_ids) > args.max_windows:
                log.info(f"Opened {args.max_windows} windows (max limit), {len(bioguide_ids) - args.max_windows} extractions not shown")
            else:
                log.warning(f"Failed to open validation windows for {failed_count} bioguide IDs")
    
    else:
        parser.print_help()
        sys.exit(1)
    
    # Print staging summary
    staging_summary = staging_manager.get_staging_summary()
    log.info(f"Staging summary: {staging_summary}")

if __name__ == "__main__":
    main()