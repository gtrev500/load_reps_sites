#!/usr/bin/env python3

import argparse
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our modules
from district_offices import (
    get_bioguides_without_district_offices,
    get_contact_page_url, 
    check_district_office_exists
)
from district_offices.core.scraper import extract_html
from district_offices.processing.llm_processor import LLMProcessor
from district_offices.utils.logging import ProvenanceTracker
from district_offices.storage.sqlite_db import SQLiteDatabase
from district_offices.storage.postgres_sync import PostgreSQLSyncManager
from district_offices.storage.models import Extraction
from district_offices.config import Config

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

def process_single_bioguide(
    bioguide_id: str, 
    database_uri: str,
    tracker: ProvenanceTracker,
    api_key: str = None,
    force: bool = False
) -> bool:
    """Process a single bioguide ID: scrape HTML, send to LLM, store results.
    
    Args:
        bioguide_id: The bioguide ID to process
        database_uri: URI for the database connection
        tracker: ProvenanceTracker instance
        api_key: Optional Anthropic API key
        force: Whether to force processing even if data already exists
        
    Returns:
        True if the processing was successful, False otherwise
    """
    # Get SQLite database instance
    db_path = Config.get_sqlite_db_path()
    db = SQLiteDatabase(str(db_path))
    
    # Start tracking the process - this creates an extraction record
    log_path = tracker.log_process_start(bioguide_id)
    
    # Extract extraction_id from log_path
    extraction_id = None
    if log_path.startswith("extraction:"):
        extraction_id = int(log_path.split(":")[1])
    
    try:
        # Step 1: Check if extraction already exists (unless forced)
        if not force:
            # Check if there's already an extraction for this bioguide
            with db.get_session() as session:
                existing_extraction = session.query(Extraction).filter(
                    Extraction.bioguide_id == bioguide_id
                ).order_by(
                    Extraction.created_at.desc()
                ).first()
                
                if existing_extraction and existing_extraction.status in ['pending', 'validated', 'processing']:
                    status = existing_extraction.status  # Extract value while in session
                    log.info(f"Extraction already exists for {bioguide_id} with status: {status}")
                    tracker.log_process_end(log_path, "skipped", f"Extraction already exists with status: {status}")
                    return True
        
        # Step 2: Get the contact page URL
        contact_url = get_contact_page_url(bioguide_id, database_uri)
        if not contact_url:
            log.error(f"No contact page URL found for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "No contact page URL found")
            return False
        
        tracker.log_step(log_path, "get_contact_url", {"contact_url": contact_url})
        
        # Update extraction with source URL
        if extraction_id:
            db.update_extraction_source_url(extraction_id, contact_url)
        
        # Step 3: Extract HTML from the contact page
        html_content, artifact_ref = extract_html(contact_url, extraction_id=extraction_id)
        if not html_content:
            log.error(f"Failed to extract HTML for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "Failed to extract HTML")
            return False
        
        tracker.log_step(log_path, "extract_html", {"artifact_ref": artifact_ref})
        
        # Step 4: Use LLM to extract district office information
        llm_processor = LLMProcessor(model_name="claude-3-haiku-20240307", api_key=api_key)
        extracted_offices = llm_processor.extract_district_offices(html_content, bioguide_id, extraction_id)
        
        # Save the extracted offices as an artifact
        tracker.save_json_artifact(log_path, "extracted_offices", {"offices": extracted_offices})
        
        if not extracted_offices:
            log.warning(f"No district offices found for {bioguide_id}")
            tracker.log_process_end(log_path, "completed", "No district offices found")
            return True
        
        # Step 5: Store the extracted office information in SQLite
        if extraction_id:
            for office in extracted_offices:
                db.create_extracted_office(extraction_id, office)
            log.info(f"Stored {len(extracted_offices)} extracted offices for {bioguide_id}")
        
        # Update extraction status to indicate it's ready for validation
        if extraction_id:
            db.update_extraction_status(extraction_id, "pending")
            log.info(f"Extraction {extraction_id} marked as pending validation")
        
        tracker.log_process_end(log_path, "extracted", f"Extracted {len(extracted_offices)} offices, pending validation")
        log.info(f"Successfully extracted {len(extracted_offices)} district offices for {bioguide_id} - pending validation")
        
        return True
    except Exception as e:
        log.error(f"Error processing {bioguide_id}: {e}")
        tracker.log_process_end(log_path, "failed", f"Error: {str(e)}")
        if extraction_id:
            db.update_extraction_status(extraction_id, "failed")
            db.update_extraction_error(extraction_id, str(e))
        return False

def main():
    """Main function for the district office scraper CLI."""
    parser = argparse.ArgumentParser(
        description="Extract district office information from congressional representatives' websites."
    )
    parser.add_argument(
        "--bioguide-id",
        type=str,
        help="Process a specific bioguide ID"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all bioguide IDs without district office information"
    )
    parser.add_argument(
        "--db-uri",
        type=str,
        help="Database URI (if not provided, uses DATABASE_URI environment variable)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Anthropic API key (if not provided, uses ANTHROPIC_API_KEY environment variable)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force processing even if district office data already exists"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG) # Ensure root logger is also set for full verbosity
        log.setLevel(logging.DEBUG)
    
    database_uri = args.db_uri or os.environ.get("DATABASE_URI")
    if not database_uri:
        log.error("Database URI not provided and DATABASE_URI environment variable not set.")
        sys.exit(1)

    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    # No longer exiting if API key is missing, LLMProcessor handles simulation
    # if not api_key:
    #     log.error("Anthropic API key not provided and ANTHROPIC_API_KEY environment variable not set.")
    #     sys.exit(1)

    tracker = ProvenanceTracker()

    # Initialize database and sync manager
    log.info("Initializing database connections and performing initial sync...")
    try:
        sqlite_db_path = Config.get_sqlite_db_path()
        sqlite_db = SQLiteDatabase(str(sqlite_db_path))
        sync_manager = PostgreSQLSyncManager(database_uri, sqlite_db)

        log.info("Syncing members from upstream PostgreSQL...")
        sync_manager.sync_members_from_upstream()
        log.info("Syncing contacts from upstream PostgreSQL...")
        sync_manager.sync_contacts_from_upstream()
        log.info("Initial sync completed.")
    except Exception as e:
        log.error(f"Failed to initialize database or perform initial sync: {e}")
        sys.exit(1)

    if args.bioguide_id:
        # Process a single bioguide ID
        log.info(f"Processing bioguide ID: {args.bioguide_id}")
        success = process_single_bioguide(
            args.bioguide_id,
            database_uri,
            tracker,
            api_key,
            args.force
        )
        
        if success:
            log.info(f"Successfully processed {args.bioguide_id}")
        else:
            log.error(f"Failed to process {args.bioguide_id}")
    
    elif args.all:
        # Process all bioguide IDs without district office information
        log.info("Processing all bioguide IDs without district office information")
        bioguide_ids = get_bioguides_without_district_offices(database_uri)
        
        if not bioguide_ids:
            log.info("No bioguide IDs found without district office information")
            sys.exit(0)
        
        log.info(f"Found {len(bioguide_ids)} bioguide IDs without district office information")
        
        success_count = 0
        failure_count = 0
        
        for bioguide_id in bioguide_ids:
            log.info(f"Processing bioguide ID: {bioguide_id}")
            success = process_single_bioguide(
                bioguide_id,
                database_uri,
                tracker,
                api_key,
                args.force
            )
            
            if success:
                success_count += 1
                log.info(f"Successfully processed {bioguide_id}")
            else:
                failure_count += 1
                log.error(f"Failed to process {bioguide_id}")
        
        log.info(f"Processed {len(bioguide_ids)} bioguide IDs: {success_count} successful, {failure_count} failed")
    
    else:
        parser.print_help()
        sys.exit(1)
    
    # Generate and print summary
    summary = tracker.generate_summary()
    log.info(f"Run summary: {summary}")

if __name__ == "__main__":
    main()