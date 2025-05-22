#!/usr/bin/env python3

import argparse
import logging
import os
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Any
from dataclasses import dataclass

# Import our modules
import database
from district_office_scraper import process_single_bioguide
from staging_manager import StagingManager
from logging_utils import ProvenanceTracker

# --- Logging Setup ---
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
    processing_time: float = 0.0

class AsyncScraper:
    """Asynchronous scraper for processing multiple bioguide IDs in parallel."""
    
    def __init__(
        self,
        database_uri: str,
        api_key: Optional[str] = None,
        staging_dir: Optional[str] = None,
        max_workers: int = 5
    ):
        """Initialize the async scraper.
        
        Args:
            database_uri: Database connection URI
            api_key: Anthropic API key
            staging_dir: Custom staging directory
            max_workers: Maximum number of concurrent workers
        """
        self.database_uri = database_uri
        self.api_key = api_key
        self.max_workers = max_workers
        
        # Initialize staging manager
        self.staging_manager = StagingManager(staging_dir)
        log.info(f"Staging manager initialized: {self.staging_manager.staging_root}")
        
        # Thread-safe tracking
        self._lock = threading.Lock()
        self._results = []
        
    def extract_single_async(
        self,
        bioguide_id: str,
        force: bool = False
    ) -> ProcessingResult:
        """Extract data for a single bioguide ID asynchronously.
        
        Args:
            bioguide_id: The bioguide ID to process
            force: Whether to force processing even if data exists
            
        Returns:
            ProcessingResult with the outcome
        """
        start_time = time.time()
        
        try:
            # Create a separate tracker for this thread
            tracker = ProvenanceTracker()
            
            # Process the bioguide ID in async mode
            success = process_single_bioguide(
                bioguide_id=bioguide_id,
                database_uri=self.database_uri,
                tracker=tracker,
                api_key=self.api_key,
                skip_validation=True,  # Always skip in async mode
                skip_storage=True,     # Always skip in async mode
                force=force,
                async_mode=True,
                staging_manager=self.staging_manager
            )
            
            processing_time = time.time() - start_time
            
            if success:
                log.info(f"Successfully processed {bioguide_id} in {processing_time:.2f}s")
                return ProcessingResult(
                    bioguide_id=bioguide_id,
                    success=True,
                    processing_time=processing_time
                )
            else:
                log.error(f"Failed to process {bioguide_id}")
                return ProcessingResult(
                    bioguide_id=bioguide_id,
                    success=False,
                    error_message="Processing failed",
                    processing_time=processing_time
                )
                
        except Exception as e:
            processing_time = time.time() - start_time
            error_msg = f"Exception processing {bioguide_id}: {str(e)}"
            log.error(error_msg)
            
            # Mark as failed in staging
            self.staging_manager.mark_failed(bioguide_id, error_msg)
            
            return ProcessingResult(
                bioguide_id=bioguide_id,
                success=False,
                error_message=error_msg,
                processing_time=processing_time
            )
    
    def process_batch(
        self,
        bioguide_ids: List[str],
        force: bool = False
    ) -> Dict[str, Any]:
        """Process a batch of bioguide IDs in parallel.
        
        Args:
            bioguide_ids: List of bioguide IDs to process
            force: Whether to force processing even if data exists
            
        Returns:
            Dictionary with processing summary
        """
        if not bioguide_ids:
            log.info("No bioguide IDs to process")
            return {"total": 0, "success": 0, "failed": 0, "results": []}
        
        log.info(f"Processing {len(bioguide_ids)} bioguide IDs with {self.max_workers} workers")
        start_time = time.time()
        
        results = []
        success_count = 0
        failed_count = 0
        
        # Process bioguide IDs in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_bioguide = {
                executor.submit(self.extract_single_async, bioguide_id, force): bioguide_id
                for bioguide_id in bioguide_ids
            }
            
            # Process completed tasks
            for future in as_completed(future_to_bioguide):
                try:
                    result = future.result()
                    results.append(result)
                    
                    if result.success:
                        success_count += 1
                    else:
                        failed_count += 1
                        
                    # Log progress
                    completed = len(results)
                    log.info(f"Progress: {completed}/{len(bioguide_ids)} completed "
                            f"({success_count} success, {failed_count} failed)")
                    
                except Exception as e:
                    bioguide_id = future_to_bioguide[future]
                    log.error(f"Exception in future for {bioguide_id}: {e}")
                    failed_count += 1
                    results.append(ProcessingResult(
                        bioguide_id=bioguide_id,
                        success=False,
                        error_message=f"Future exception: {str(e)}"
                    ))
        
        total_time = time.time() - start_time
        
        summary = {
            "total": len(bioguide_ids),
            "success": success_count,
            "failed": failed_count,
            "total_time": total_time,
            "avg_time_per_item": total_time / len(bioguide_ids) if bioguide_ids else 0,
            "results": results
        }
        
        log.info(f"Batch processing complete: {success_count}/{len(bioguide_ids)} successful "
                f"in {total_time:.2f}s (avg: {summary['avg_time_per_item']:.2f}s per item)")
        
        return summary
    
    def process_all_missing(self, force: bool = False) -> Dict[str, Any]:
        """Process all bioguide IDs that don't have district office information.
        
        Args:
            force: Whether to force processing even if data exists
            
        Returns:
            Dictionary with processing summary
        """
        log.info("Fetching bioguide IDs without district office information")
        bioguide_ids = database.get_bioguides_without_district_offices(self.database_uri)
        
        if not bioguide_ids:
            log.info("No bioguide IDs found without district office information")
            return {"total": 0, "success": 0, "failed": 0, "results": []}
        
        log.info(f"Found {len(bioguide_ids)} bioguide IDs without district office information")
        return self.process_batch(bioguide_ids, force)

def main():
    """Main function for the async scraper."""
    parser = argparse.ArgumentParser(
        description="Asynchronously scrape district office information from representative contact pages."
    )
    parser.add_argument(
        "--bioguide-ids",
        type=str,
        nargs="+",
        help="Process specific bioguide IDs"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all bioguide IDs without district office information"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Process bioguide IDs from a file (one per line)"
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
        "--staging-dir",
        type=str,
        help="Custom staging directory path"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Maximum number of concurrent workers (default: 5)"
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
    
    # Validate max_workers
    if args.max_workers < 1:
        log.error("max-workers must be at least 1")
        sys.exit(1)
    
    # Initialize async scraper
    scraper = AsyncScraper(
        database_uri=database_uri,
        api_key=api_key,
        staging_dir=args.staging_dir,
        max_workers=args.max_workers
    )
    
    # Determine bioguide IDs to process
    bioguide_ids = []
    
    if args.bioguide_ids:
        bioguide_ids = args.bioguide_ids
        log.info(f"Processing specified bioguide IDs: {bioguide_ids}")
    
    elif args.file:
        if not os.path.exists(args.file):
            log.error(f"File not found: {args.file}")
            sys.exit(1)
        
        try:
            with open(args.file, 'r') as f:
                bioguide_ids = [line.strip() for line in f if line.strip()]
            log.info(f"Loaded {len(bioguide_ids)} bioguide IDs from {args.file}")
        except Exception as e:
            log.error(f"Error reading file {args.file}: {e}")
            sys.exit(1)
    
    elif args.all:
        log.info("Processing all bioguide IDs without district office information")
        summary = scraper.process_all_missing(args.force)
    
    else:
        parser.print_help()
        sys.exit(1)
    
    # Process bioguide IDs if we have a specific list
    if bioguide_ids:
        summary = scraper.process_batch(bioguide_ids, args.force)
    
    # Print summary
    if 'summary' in locals():
        print(f"\nProcessing Summary:")
        print(f"Total: {summary['total']}")
        print(f"Successful: {summary['success']}")
        print(f"Failed: {summary['failed']}")
        print(f"Total time: {summary['total_time']:.2f}s")
        print(f"Average time per item: {summary['avg_time_per_item']:.2f}s")
        
        # Print failed items
        failed_items = [r for r in summary['results'] if not r.success]
        if failed_items:
            print(f"\nFailed items:")
            for result in failed_items:
                print(f"  {result.bioguide_id}: {result.error_message}")
    
    # Print staging summary
    staging_summary = scraper.staging_manager.get_staging_summary()
    print(f"\nStaging Summary:")
    print(f"Total extractions: {staging_summary['total_extractions']}")
    print(f"Status counts: {staging_summary['status_counts']}")

if __name__ == "__main__":
    main()