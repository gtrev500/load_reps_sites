#!/usr/bin/env python3

import argparse
import logging
import os
import sys
import time
from typing import List, Dict, Optional, Any

# Import our modules
import database
from scraper import extract_html, clean_html, extract_contact_sections, capture_screenshot
from llm_processor import LLMProcessor
from validation import ValidationInterface
from logging_utils import ProvenanceTracker

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

def process_single_bioguide(
    bioguide_id: str, 
    database_uri: str,
    tracker: ProvenanceTracker,
    api_key: Optional[str] = None,
    skip_validation: bool = False,
    skip_storage: bool = False
) -> bool:
    """Process a single bioguide ID.
    
    Args:
        bioguide_id: The bioguide ID to process
        database_uri: URI for the database connection
        tracker: ProvenanceTracker instance
        api_key: Optional Anthropic API key
        skip_validation: Whether to skip human validation
        skip_storage: Whether to skip database storage
        
    Returns:
        True if the processing was successful, False otherwise
    """
    # Start tracking the process
    log_path = tracker.log_process_start(bioguide_id)
    
    try:
        # Step 1: Check if district office information already exists
        if database.check_district_office_exists(bioguide_id, database_uri):
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
        
        # Step 4: Capture a screenshot (or HTML reference)
        screenshot_path = capture_screenshot(html_path, bioguide_id)
        tracker.log_step(log_path, "capture_screenshot", {"screenshot_path": screenshot_path})
        
        # Step 5: Clean and extract relevant HTML sections
        cleaned_html = clean_html(html_content)
        contact_sections = extract_contact_sections(cleaned_html)
        
        # Save the cleaned HTML and contact sections as artifacts
        tracker.save_artifact(log_path, "cleaned_html", cleaned_html, "html")
        tracker.save_artifact(log_path, "contact_sections", contact_sections, "html")
        
        # Step 6: Use LLM to extract district office information
        llm_processor = LLMProcessor(api_key)
        extracted_offices = llm_processor.extract_district_offices(contact_sections, bioguide_id)
        
        # Save the extracted offices as an artifact
        tracker.save_json_artifact(log_path, "extracted_offices", {"offices": extracted_offices})
        
        if not extracted_offices:
            log.warning(f"No district offices found for {bioguide_id}")
            tracker.log_process_end(log_path, "completed", "No district offices found")
            return True
        
        # Step 7: Validate the extracted information (if not skipped)
        if not skip_validation:
            validation_interface = ValidationInterface()
            validation_html_path = validation_interface.generate_validation_html(
                bioguide_id, html_content, extracted_offices, contact_url
            )
            
            is_valid, validated_offices = validation_interface.validate_office_data(
                bioguide_id, extracted_offices, html_content, contact_url
            )
            
            tracker.log_validation_artifacts(log_path, validation_html_path, extracted_offices, is_valid)
            
            if not is_valid:
                log.warning(f"Extraction rejected for {bioguide_id}")
                tracker.log_process_end(log_path, "rejected", "Human validation rejected the extraction")
                return False
            
            offices_to_store = validated_offices
        else:
            log.info(f"Skipping validation for {bioguide_id}")
            offices_to_store = extracted_offices
        
        # Step 8: Store the district office information (if not skipped)
        if not skip_storage:
            success = False
            for office in offices_to_store:
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
        else:
            log.info(f"Skipping storage for {bioguide_id}")
            tracker.log_process_end(log_path, "completed", "Storage skipped")
        
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
        "--skip-validation",
        action="store_true",
        help="Skip human validation of extracted information"
    )
    parser.add_argument(
        "--skip-storage",
        action="store_true",
        help="Skip storing information in the database"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="Anthropic API key (if not provided, uses ANTHROPIC_API_KEY environment variable)"
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
            args.skip_validation,
            args.skip_storage
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
                args.skip_validation,
                args.skip_storage
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