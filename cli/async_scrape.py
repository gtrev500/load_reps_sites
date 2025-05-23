#!/usr/bin/env python3
"""Unified async CLI for district office extraction."""

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import async modules
from district_offices.storage.async_database import (
    get_connection_pool,
    close_connection_pool,
    check_district_office_exists,
    get_contact_page_url,
    get_bioguides_without_district_offices,
    store_district_office,
)
from district_offices.core.async_scraper import (
    extract_html,
    clean_html,
    extract_contact_sections,
    capture_screenshot,
)
from district_offices.processing.async_llm_processor import AsyncLLMProcessor
from district_offices.validation.async_interface import AsyncValidationInterface
from district_offices.utils.logging import ProvenanceTracker
from district_offices.storage.staging import StagingManager

# Logging setup
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a single bioguide ID."""
    bioguide_id: str
    success: bool
    error_message: Optional[str] = None
    offices_found: int = 0


async def process_single_bioguide(
    bioguide_id: str,
    database_uri: str,
    tracker: ProvenanceTracker,
    api_key: Optional[str] = None,
    skip_validation: bool = False,
    skip_storage: bool = False,
    force: bool = False,
    async_mode: bool = False,
    staging_manager: Optional[StagingManager] = None,
    browser_validation: bool = False,
) -> ProcessingResult:
    """Process a single bioguide ID asynchronously.
    
    Args:
        bioguide_id: The bioguide ID to process
        database_uri: URI for the database connection
        tracker: ProvenanceTracker instance
        api_key: Optional API key for LLM
        skip_validation: Whether to skip human validation
        skip_storage: Whether to skip database storage
        force: Whether to force processing even if data exists
        async_mode: Whether to save to staging for later validation
        staging_manager: StagingManager instance for async mode
        browser_validation: Whether to use browser-based validation
        
    Returns:
        ProcessingResult with success status and details
    """
    start_time = time.time()
    
    try:
        # Track this extraction
        log_path = tracker.log_process_start(bioguide_id)
        
        # Check if data already exists
        if not force and await check_district_office_exists(bioguide_id, database_uri):
            log.info(f"District office data already exists for {bioguide_id}")
            tracker.log_process_end(log_path, "skipped", "Already exists")
            return ProcessingResult(bioguide_id, True, "Already exists")
        
        # Get contact page URL
        contact_url = await get_contact_page_url(bioguide_id, database_uri)
        if not contact_url:
            log.error(f"No contact page URL found for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "No contact URL")
            return ProcessingResult(bioguide_id, False, "No contact URL")
        
        log.info(f"Processing {bioguide_id} - Contact URL: {contact_url}")
        tracker.log_step(log_path, "contact_url_retrieved", {"url": contact_url})
        
        # Extract HTML
        html_content, html_path = await extract_html(contact_url)
        if not html_content:
            log.error(f"Failed to extract HTML for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "Failed to extract HTML")
            return ProcessingResult(bioguide_id, False, "Failed to extract HTML")
        
        tracker.log_step(log_path, "html_extracted", {"cache_path": html_path})
        
        # Clean HTML and extract sections
        cleaned_html = clean_html(html_content)
        contact_sections = extract_contact_sections(cleaned_html)
        
        if not contact_sections:
            log.warning(f"No contact sections found for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "No contact sections found")
            return ProcessingResult(bioguide_id, False, "No contact sections found")
        
        log.info(f"Found {len(contact_sections)} contact sections")
        tracker.log_step(log_path, "sections_extracted", {"count": len(contact_sections)})
        
        # Capture screenshot
        #screenshot_path = await capture_screenshot(contact_url)
        #if screenshot_path:
        #    tracker.log_step(log_path, "screenshot_captured", {"path": screenshot_path})
        
        # Process with LLM
        llm_processor = AsyncLLMProcessor(api_key=api_key)
        offices = await llm_processor.extract_district_offices(
            contact_sections, 
            bioguide_id
        )
        
        if not offices:
            log.error(f"LLM failed to extract offices for {bioguide_id}")
            tracker.log_process_end(log_path, "failed", "LLM extraction failed")
            return ProcessingResult(bioguide_id, False, "LLM extraction failed")
        
        log.info(f"LLM extracted {len(offices)} offices")
        tracker.log_step(log_path, "llm_extraction_complete", {"offices_count": len(offices)})
        
        # In async mode, save to staging and return
        if async_mode and staging_manager:
            # Prepare artifacts
            artifacts = {}
            if html_path and os.path.exists(html_path):
                artifacts['html'] = html_path
            
            # Save contact sections to a file
            sections_path = os.path.join(os.path.dirname(html_path) if html_path else '/tmp', 
                                       f"{bioguide_id}_sections.html")
            with open(sections_path, 'w', encoding='utf-8') as f:
                f.write('\n\n'.join(contact_sections))
            artifacts['contact_sections'] = sections_path
            
            # Save extraction to staging
            staging_manager.save_extraction(
                bioguide_id=bioguide_id,
                source_url=contact_url,
                extracted_offices=offices,
                artifacts=artifacts,
                provenance_log=log_path,
                metadata={'offices_count': len(offices)}
            )
            log.info(f"Saved {bioguide_id} to staging for later validation")
            tracker.log_process_end(log_path, "success", "Saved to staging")
            return ProcessingResult(bioguide_id, True, "Saved to staging", len(offices))
        
        # Human validation (if not skipped)
        if not skip_validation:
            validator = AsyncValidationInterface()
            validated_offices = await validator.validate_offices(
                offices,
                contact_sections,
                bioguide_id,
                #screenshot_path,
                use_browser=browser_validation
            )
            
            if not validated_offices:
                log.info(f"Validation rejected for {bioguide_id}")
                tracker.log_step(log_path, "validation_rejected", {})
                tracker.log_process_end(log_path, "failed", "Validation rejected")
                return ProcessingResult(bioguide_id, False, "Validation rejected")
            
            offices = validated_offices
            tracker.log_step(log_path, "validation_complete", {"offices_count": len(offices)})
        
        # Store in database (if not skipped)
        if not skip_storage:
            stored_count = 0
            for office in offices:
                success = await store_district_office(office, database_uri)
                if success:
                    stored_count += 1
                    tracker.log_step(log_path, "office_stored", {"office_id": office.get('office_id')})
            
            if stored_count == 0:
                tracker.log_process_end(log_path, "failed", "Failed to store offices")
                return ProcessingResult(bioguide_id, False, "Failed to store offices")
            
            log.info(f"Stored {stored_count} offices for {bioguide_id}")
        
        # Complete tracking
        elapsed_time = time.time() - start_time
        tracker.log_process_end(log_path, "success", f"Completed in {elapsed_time:.2f}s")
        
        return ProcessingResult(bioguide_id, True, "Success", len(offices))
        
    except Exception as e:
        log.error(f"Error processing {bioguide_id}: {str(e)}")
        tracker.log_process_end(log_path, "failed", str(e))
        return ProcessingResult(bioguide_id, False, f"Exception: {str(e)}")


async def process_multiple_bioguides(
    bioguide_ids: List[str],
    database_uri: str,
    tracker: ProvenanceTracker,
    api_key: Optional[str] = None,
    max_concurrent: int = 5,
    **kwargs
) -> Dict[str, ProcessingResult]:
    """Process multiple bioguide IDs concurrently.
    
    Args:
        bioguide_ids: List of bioguide IDs to process
        database_uri: Database connection URI
        tracker: ProvenanceTracker instance
        api_key: Optional API key for LLM
        max_concurrent: Maximum concurrent tasks
        **kwargs: Additional arguments passed to process_single_bioguide
        
    Returns:
        Dictionary mapping bioguide_id to ProcessingResult
    """
    results = {}
    
    # Create semaphore to limit concurrency
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_with_semaphore(bioguide_id: str):
        async with semaphore:
            result = await process_single_bioguide(
                bioguide_id, database_uri, tracker, api_key, **kwargs
            )
            return bioguide_id, result
    
    # Process all bioguides concurrently
    tasks = [process_with_semaphore(bid) for bid in bioguide_ids]
    
    # Use tqdm for progress if available
    try:
        from tqdm.asyncio import tqdm_asyncio
        completed = await tqdm_asyncio.gather(*tasks, desc="Processing")
    except ImportError:
        completed = await asyncio.gather(*tasks)
    
    # Collect results
    for bioguide_id, result in completed:
        results[bioguide_id] = result
    
    return results


async def main():
    """Main async entry point."""
    parser = argparse.ArgumentParser(
        description="Scrape district office information from representative contact pages."
    )
    parser.add_argument(
        "--bioguide-id",
        help="Process a specific bioguide ID"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all bioguide IDs without district office information"
    )
    parser.add_argument(
        "--db-uri",
        help="Database URI (if not provided, uses DATABASE_URI environment variable)"
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip human validation of extracted information"
    )
    parser.add_argument(
        "--browser-validation",
        action="store_true",
        help="Use browser-based validation with Accept/Reject buttons"
    )
    parser.add_argument(
        "--skip-storage",
        action="store_true",
        help="Skip storing information in the database"
    )
    parser.add_argument(
        "--api-key",
        help="LLM API key (if not provided, uses ANTHROPIC_API_KEY environment variable)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force processing even if district office data already exists"
    )
    parser.add_argument(
        "--async-mode",
        action="store_true",
        help="Run in async mode (saves extractions to staging for later validation)"
    )
    parser.add_argument(
        "--staging-dir",
        help="Custom staging directory path (for async mode)"
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent processing tasks (default: 5)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Get database URI
    database_uri = args.db_uri or os.environ.get("DATABASE_URI")
    if not database_uri:
        log.error("Database URI not provided. Use --db-uri or set DATABASE_URI environment variable.")
        sys.exit(1)
    
    # Get API key
    api_key = args.api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        log.warning("API key not provided. Will attempt to use environment variables.")
    
    # Initialize provenance tracker
    tracker = ProvenanceTracker()
    
    # Initialize staging manager if in async mode
    staging_manager = None
    if args.async_mode:
        staging_dir = args.staging_dir or os.path.join(
            os.path.dirname(__file__), "..", "data", "staging"
        )
        staging_manager = StagingManager(staging_dir)
        log.info(f"Async mode enabled, using staging directory: {staging_dir}")
    
    try:
        # Process single bioguide ID
        if args.bioguide_id:
            log.info(f"Processing single bioguide ID: {args.bioguide_id}")
            result = await process_single_bioguide(
                args.bioguide_id,
                database_uri,
                tracker,
                api_key=api_key,
                skip_validation=args.skip_validation,
                skip_storage=args.skip_storage,
                force=args.force,
                async_mode=args.async_mode,
                staging_manager=staging_manager,
                browser_validation=args.browser_validation,
            )
            
            if result.success:
                log.info(f"Successfully processed {args.bioguide_id}")
            else:
                log.error(f"Failed to process {args.bioguide_id}: {result.error_message}")
                sys.exit(1)
        
        # Process all bioguide IDs
        elif args.all:
            log.info("Processing all bioguide IDs without district office information")
            bioguide_ids = await get_bioguides_without_district_offices(database_uri)
            
            if not bioguide_ids:
                log.info("No bioguide IDs found without district office information")
                sys.exit(0)
            
            log.info(f"Found {len(bioguide_ids)} bioguide IDs to process")
            
            # Process concurrently
            results = await process_multiple_bioguides(
                bioguide_ids,
                database_uri,
                tracker,
                api_key=api_key,
                max_concurrent=args.max_concurrent,
                skip_validation=args.skip_validation,
                skip_storage=args.skip_storage,
                force=args.force,
                async_mode=args.async_mode,
                staging_manager=staging_manager,
                browser_validation=args.browser_validation,
            )
            
            # Summary statistics
            success_count = sum(1 for r in results.values() if r.success)
            failure_count = len(results) - success_count
            total_offices = sum(r.offices_found for r in results.values())
            
            log.info(f"\n=== Processing Summary ===")
            log.info(f"Total processed: {len(results)}")
            log.info(f"Successful: {success_count}")
            log.info(f"Failed: {failure_count}")
            log.info(f"Total offices found: {total_offices}")
            
            if failure_count > 0:
                log.info("\nFailed bioguide IDs:")
                for bid, result in results.items():
                    if not result.success:
                        log.info(f"  {bid}: {result.error_message}")
        
        else:
            parser.error("Please specify --bioguide-id or --all")
    
    finally:
        # Close connection pool
        await close_connection_pool()
        
        # Generate summary
        summary = tracker.generate_summary()
        log.info(f"Run summary: {summary}")


def run():
    """Synchronous entry point that runs the async main."""
    asyncio.run(main())


if __name__ == "__main__":
    run()