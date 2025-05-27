#!/usr/bin/env python3

import argparse
import logging
import os
import sys
from typing import List, Dict, Optional, Any
import time

# Add parent directory to path for imports when run as script
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Import our modules
from district_offices import (
    StagingManager, 
    ExtractionStatus,
    store_district_office,
    ProvenanceTracker,
    # store_district_office # This is now called by the server
)
from district_offices.validation.interface import ValidationInterface
from district_offices.validation.server import ValidationServer # Import the server

# Import SQLite database for artifact loading (can be removed if server handles its own DB)
# _sqlite_db = None

# def _get_sqlite_db():
#     """Get SQLite database instance (lazy loading)."""
#     global _sqlite_db
#     if _sqlite_db is None:
#         from district_offices.storage.sqlite_db import SQLiteDatabase
#         from district_offices.config import Config
#         db_path = Config.get_sqlite_db_path()
#         _sqlite_db = SQLiteDatabase(str(db_path))
#     return _sqlite_db

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)


def run_validation_server(
    bioguide_ids: List[str],
    staging_manager: StagingManager,
    database_uri: Optional[str] = None
) -> None:
    """
    Initializes and starts the ValidationServer for the given bioguide IDs.
    The server will run until all items are processed or it's manually stopped.
    """
    if not bioguide_ids:
        log.info("No bioguide IDs provided for validation.")
        return

    validation_interface = ValidationInterface()
    
    # The server will run on an automatically selected port or a predefined one if specified
    server = ValidationServer(
        pending_bioguides=bioguide_ids,
        staging_manager=staging_manager,
        validation_interface=validation_interface,
        database_uri=database_uri,
        port=0 # Auto-select port
    )
    
    log.info(f"Starting validation server for {len(bioguide_ids)} item(s)...")
    server.start() # This will also trigger the first item to be processed

    # Keep the main thread alive while the server's daemon thread runs
    # Or implement a more graceful shutdown mechanism if needed (e.g., server sets an event)
    try:
        while server.server_thread and server.server_thread.is_alive():
            # Check if all items have been processed if server doesn't stop itself
            if server.current_item_index >= len(server.pending_bioguides):
                log.info("All items processed by the server.")
                break
            time.sleep(1) # Keep alive, server is on a daemon thread
    except KeyboardInterrupt:
        log.info("Keyboard interrupt received. Stopping server...")
    finally:
        server.stop()
        log.info("Validation process finished.")


def validate_all_pending(
    staging_manager: StagingManager,
    database_uri: Optional[str] = None,
    batch_size: Optional[int] = None
) -> Dict[str, Any]:
    """
    Validate pending extractions using the server-orchestrated browser workflow.
    
    Args:
        staging_manager: StagingManager instance.
        database_uri: Database URI for storage (e.g., PostgreSQL).
        batch_size: Maximum number of extractions to validate in this run.
        
    Returns:
        Dictionary with a summary of items queued for validation.
    """
    # Load only PENDING extractions for validation
    # StagingManager.load_pending_extractions() should ideally return only those needing validation.
    # If it returns other statuses, they should be filtered.
    # For now, assume it returns bioguide_ids of PENDING extractions.
    all_pending_bioguides = staging_manager.load_pending_extractions()
    
    # Filter for truly pending items if staging_manager returns more than that
    # This step might be redundant if load_pending_extractions is accurate
    actually_pending_ids = []
    for bg_id in all_pending_bioguides:
        extraction_data = staging_manager.get_extraction_data(bg_id)
        if extraction_data and extraction_data.status == ExtractionStatus.PENDING:
            actually_pending_ids.append(bg_id)
        elif not extraction_data:
            log.warning(f"Could not get extraction data for {bg_id} listed as pending.")

    if not actually_pending_ids:
        log.info("No truly pending extractions found to validate.")
        return {"queued_for_validation": 0, "total_pending_before": len(all_pending_bioguides)}

    log.info(f"Found {len(actually_pending_ids)} PENDING extractions to validate (out of {len(all_pending_bioguides)} initially listed).")
    
    bioguides_to_validate = actually_pending_ids
    if batch_size and batch_size > 0 and batch_size < len(actually_pending_ids):
        bioguides_to_validate = actually_pending_ids[:batch_size]
        log.info(f"Processing a batch of {len(bioguides_to_validate)} extractions due to batch_size={batch_size}.")
    
    run_validation_server(bioguides_to_validate, staging_manager, database_uri)
    
    # Summary after server run (could be more sophisticated by getting results from server)
    # For now, just report what was queued.
    # The server logs individual outcomes.
    final_summary = staging_manager.get_staging_summary()
    log.info(f"Staging summary after validation run: {final_summary}")
    
    return {
        "queued_for_validation": len(bioguides_to_validate),
        "total_pending_before": len(all_pending_bioguides), # Original count before this run's filtering
        "current_staging_summary": final_summary
    }


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
        help="Validate all pending extractions using the browser-based server."
    )
    # The --force flag's behavior might need reconsideration with the new server model.
    # For now, it's not directly used by run_validation_server, which relies on StagingManager's list.
    # If --force means re-validating even non-PENDING items, StagingManager logic would need adjustment
    # or a different list of bioguides passed to the server.
    # parser.add_argument(
    #     "--force",
    #     action="store_true",
    #     help="Re-validate previously processed extractions (behavior may vary)"
    # )
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
    log.info("Staging manager initialized with SQLite backend")
    
    # Validate specific bioguide ID
    if args.bioguide_id:
        log.info(f"Validating specific bioguide ID: {args.bioguide_id} using server.")
        # Ensure this bioguide ID is actually pending or handle --force if re-implemented
        extraction_data = staging_manager.get_extraction_data(args.bioguide_id)
        if not extraction_data:
            log.error(f"No extraction data found for {args.bioguide_id}. Cannot validate.")
            sys.exit(1)
        
        # if extraction_data.status != ExtractionStatus.PENDING and not args.force:
        #    log.warning(f"Extraction for {args.bioguide_id} is not pending (status: {extraction_data.status.value}). Use --force to re-validate.")
        #    sys.exit(0)
            
        run_validation_server([args.bioguide_id], staging_manager, database_uri)
    
    # Validate all pending extractions
    elif args.all_pending:
        log.info("Validating all pending extractions using server.")
        summary = validate_all_pending(staging_manager, database_uri, args.batch_size)
        log.info(f"Validation queuing complete. Summary: Queued {summary.get('queued_for_validation', 0)} items.")
        # Detailed outcomes are logged by the server.
    
    else:
        parser.print_help()
        sys.exit(1)
    
    # Print staging summary
    staging_summary = staging_manager.get_staging_summary()
    log.info(f"Staging summary: {staging_summary}")

if __name__ == "__main__":
    main()
