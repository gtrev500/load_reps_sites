#!/usr/bin/env python3

import argparse
import logging
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our modules
from district_offices.storage import database
from district_offices.core.scraper import extract_html
from district_offices.processing.llm_processor import LLMProcessor
from district_offices.utils.logging import ProvenanceTracker

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
    # Start tracking the process
    log_path = tracker.log_process_start(bioguide_id)
    
    try:
        # Step 1: Check if district office information already exists (unless forced)
        if not force and database.check_district_office_exists(bioguide_id, database_uri):
            log.info(f"District office information already exists for {bioguide_id}")
            tracker.log_process_end(log_path, "skipped", "District office information already exists")
            return True
        
        # Step 2: Get the contact page URL
        contact_url = database.get_contact_page_url(bioguide_id, database_uri)
        if not contact_url:
            log.error(f"No contact page URL found for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "No contact page URL found")
            return False
        
        tracker.log_step(log_path, "get_contact_url", {"contact_url": contact_url})
        
        # Step 3: Extract HTML from the contact page
        html_content, html_path = extract_html(contact_url)
        if not html_content:
            log.error(f"Failed to extract HTML for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "Failed to extract HTML")
            return False
        
        tracker.log_step(log_path, "extract_html", {"html_path": html_path})
        
        # Step 4: Use LLM to extract district office information
        llm_processor = LLMProcessor(model_name="claude-3-haiku-20240307", api_key=api_key)
        extracted_offices = llm_processor.extract_district_offices(html_content, bioguide_id)
        
        # Save the extracted offices as an artifact
        tracker.save_json_artifact(log_path, "extracted_offices", {"offices": extracted_offices})
        
        if not extracted_offices:
            log.warning(f"No district offices found for {bioguide_id}")
            tracker.log_process_end(log_path, "completed", "No district offices found")
            return True
        
        # Step 5: Store the district office information
        success = False
        for office in extracted_offices:
            # Add the bioguide_id to each office
            office_data = office.copy()
            office_data["bioguide_id"] = bioguide_id
            
            # Store in the database
            store_success = database.store_district_office(office_data, database_uri)
            success = success or store_success
        
        if success:
            log.info(f"Successfully stored district offices for {bioguide_id}")
            tracker.log_process_end(log_path, "stored", "District offices stored in database")
        else:
            log.error(f"Failed to store district offices for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "Failed to store district offices")
            return False
        
        return True
    except Exception as e:
        log.error(f"Error processing {bioguide_id}: {e}")
        tracker.log_process_end(log_path, "failed", f"Error: {str(e)}")
        return False

def main():
    """Main function to coordinate the district office scraping process."""
    parser = argparse.ArgumentParser(
        description="Scrape district office information from representative contact pages."
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
        logging.getLogger().setLevel(logging.DEBUG)
        log.setLevel(logging.DEBUG)
    
    # Get database URI
    database_uri = args.db_uri or os.environ.get("DATABASE_URI")
    if not database_uri:
        log.error("Database URI not provided and DATABASE_URI environment variable not set")
        sys.exit(1)
    
    # Get API key
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    
    # Initialize provenance tracker
    tracker = ProvenanceTracker()
    
    # Process bioguide IDs
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
        bioguide_ids = database.get_bioguides_without_district_offices(database_uri)
        
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