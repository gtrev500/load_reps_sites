#!/usr/bin/env python3

import os
import json
import time
import threading
import logging
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
import tempfile
from typing import List, Dict, Any, Optional

# Assuming these are available in the context or will be imported
from district_offices import StagingManager, store_district_office, ExtractionStatus
from district_offices.validation.interface import ValidationInterface
from district_offices.storage.sqlite_db import SQLiteDatabase # For type hinting if passed
from district_offices.config import Config # For DB path if initializing DB here

log = logging.getLogger(__name__)

# Lazy import for SQLite
_sqlite_db_server = None

def _get_sqlite_db_server_instance():
    """Get SQLite database instance for server usage (lazy loading)."""
    global _sqlite_db_server
    if _sqlite_db_server is None:
        # This import is fine here as it's within a function
        from district_offices.storage.sqlite_db import SQLiteDatabase 
        db_path = Config.get_sqlite_db_path()
        _sqlite_db_server = SQLiteDatabase(str(db_path))
    return _sqlite_db_server


class ValidationServer:
    """HTTP server to orchestrate browser-based validation, opening new tabs."""
    
    def __init__(self, 
                 pending_bioguides: List[str],
                 staging_manager: StagingManager,
                 validation_interface: ValidationInterface,
                 database_uri: Optional[str],
                 port=0):
        """Initialize validation server.
        
        Args:
            pending_bioguides: List of bioguide IDs to validate.
            staging_manager: Instance of StagingManager.
            validation_interface: Instance of ValidationInterface.
            database_uri: URI for the upstream database (e.g., PostgreSQL).
            port: Port to listen on (0 = auto-select available port).
        """
        self.port = port
        self.pending_bioguides = pending_bioguides
        self.staging_manager = staging_manager
        self.validation_interface = validation_interface
        self.database_uri = database_uri
        
        self.current_item_index = 0
        self.server = None
        self.server_thread = None
        self.temp_dir = tempfile.mkdtemp(prefix="validation_server_") # For SimpleHTTPRequestHandler base
        self.db = _get_sqlite_db_server_instance() # SQLite instance for artifact loading

    def _get_data_for_validation(self, bioguide_id: str) -> Optional[Dict[str, Any]]:
        """Fetches all necessary data for validating a single bioguide_id."""
        extraction_data = self.staging_manager.get_extraction_data(bioguide_id)
        if not extraction_data:
            log.error(f"No extraction data found for {bioguide_id} by server.")
            return None

        html_content = ""
        contact_sections = ""
        extraction_id = None

        # Get the extraction ID from SQLite
        # This requires direct db access or a method in staging_manager
        with self.db.get_session() as session:
            from district_offices.storage.models import Extraction # Import here
            extraction_obj = session.query(Extraction).filter(
                Extraction.bioguide_id == bioguide_id
            ).order_by(
                Extraction.created_at.desc()
            ).first()
            if extraction_obj:
                extraction_id = extraction_obj.id
        
        if not extraction_id:
            log.error(f"Could not find extraction_id for {bioguide_id}")
            # Fallback: try to get it from extraction_data if it's stored there, though less reliable
            if hasattr(extraction_data, 'id') and extraction_data.id: # Check if StagingManager's ExtractionData has id
                 extraction_id = extraction_data.id
            else: # Try to get it from the artifacts dict if it's an int
                if "extraction_id" in extraction_data.artifacts and isinstance(extraction_data.artifacts["extraction_id"], int):
                    extraction_id = extraction_data.artifacts["extraction_id"]
                else: # Check if the key is a string like "artifact:123"
                    for key, val in extraction_data.artifacts.items():
                        if isinstance(val, str) and val.startswith("extraction_id:"):
                            try:
                                extraction_id = int(val.split(":")[1])
                                break
                            except ValueError:
                                pass
            if not extraction_id:
                 log.error(f"Still could not determine extraction_id for {bioguide_id} from extraction_data.")
                 return None


        # Load HTML content from artifacts
        if "html_content" in extraction_data.artifacts:
            artifact_ref = extraction_data.artifacts["html_content"]
            if isinstance(artifact_ref, str) and artifact_ref.startswith("artifact:"):
                try:
                    artifact_id = int(artifact_ref.split(":")[1])
                    content_bytes = self.db.get_artifact_content(artifact_id)
                    if content_bytes:
                        html_content = content_bytes.decode('utf-8')
                except ValueError:
                    log.error(f"Invalid artifact reference for html_content: {artifact_ref}")
        
        # Load contact sections from artifacts
        if "contact_sections" in extraction_data.artifacts:
            artifact_ref = extraction_data.artifacts["contact_sections"]
            if isinstance(artifact_ref, str) and artifact_ref.startswith("artifact:"):
                try:
                    artifact_id = int(artifact_ref.split(":")[1])
                    content_bytes = self.db.get_artifact_content(artifact_id)
                    if content_bytes:
                        contact_sections = content_bytes.decode('utf-8')
                except ValueError:
                    log.error(f"Invalid artifact reference for contact_sections: {artifact_ref}")

        return {
            "bioguide_id": bioguide_id,
            "extracted_offices": extraction_data.extracted_offices,
            "html_content": html_content,
            "source_url": extraction_data.source_url,
            "contact_sections": contact_sections,
            "extraction_id": extraction_id
        }

    def _process_next_item(self):
        """Prepares and opens the next validation item in a new tab."""
        if self.current_item_index < len(self.pending_bioguides):
            bioguide_id = self.pending_bioguides[self.current_item_index]
            log.info(f"Server processing next item: {bioguide_id} ({self.current_item_index + 1}/{len(self.pending_bioguides)})")
            
            validation_data = self._get_data_for_validation(bioguide_id)
            
            if validation_data:
                html_path = self.validation_interface.generate_validation_html(
                    bioguide_id=validation_data["bioguide_id"],
                    html_content=validation_data["html_content"],
                    extracted_offices=validation_data["extracted_offices"],
                    url=validation_data["source_url"],
                    contact_sections=validation_data["contact_sections"],
                    validation_port=self.port 
                )
                self.validation_interface.open_validation_interface_nonblocking(html_path)
            else:
                log.error(f"Failed to get data for {bioguide_id}. Skipping.")
                self.current_item_index += 1 # Ensure we move to the next
                self._process_next_item() # Try the one after that

        else:
            log.info("Validation queue complete. Server has processed all items.")
            # Optionally, the server could stop itself here or signal completion.
            # For now, it will just stay alive until manually stopped.

    def start(self):
        """Start the validation server and process the first item."""
        
        # Allow handler to access the server instance
        server_instance = self 

        class ValidationHandler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=server_instance.temp_dir, **kwargs)
            
            def do_GET(self):
                """Handle GET requests for validation responses and trigger next item."""
                parsed_path = urlparse(self.path)
                
                if parsed_path.path == '/validate':
                    query_params = parse_qs(parsed_path.query)
                    decision_str = query_params.get('decision', [None])[0]
                    bioguide_id_validated = query_params.get('bioguide_id', [None])[0]
                    
                    log.info(f"Server received validation: Bioguide {bioguide_id_validated}, Decision: {decision_str}")

                    if decision_str in ['accept', 'reject'] and bioguide_id_validated:
                        is_valid = decision_str == 'accept'
                        
                        # Fetch data needed for saving (offices, url, extraction_id)
                        # This bioguide_id should match the one at current_item_index
                        # For robustness, ensure we are saving for the correct item.
                        if bioguide_id_validated != server_instance.pending_bioguides[server_instance.current_item_index]:
                            log.warning(f"Received validation for {bioguide_id_validated}, but current server item is {server_instance.pending_bioguides[server_instance.current_item_index]}. Processing {bioguide_id_validated}.")
                        
                        # Get data again for saving, as it might not be stored on server instance directly
                        save_data = server_instance._get_data_for_validation(bioguide_id_validated)

                        if save_data:
                            extraction_id = save_data["extraction_id"]
                            offices = save_data["extracted_offices"]
                            source_url = save_data["source_url"]

                            if is_valid:
                                server_instance.validation_interface._save_validated_data(
                                    bioguide_id_validated, offices, source_url, extraction_id
                                )
                            else:
                                server_instance.validation_interface._save_rejected_data(
                                    bioguide_id_validated, offices, source_url, extraction_id
                                )
                            
                            # Mark in staging manager (SQLite)
                            server_instance.staging_manager.mark_validated(extraction_id, is_valid)

                            # Store to upstream DB if valid and URI provided
                            if is_valid and offices and server_instance.database_uri:
                                log.info(f"Auto-storing validated offices for {bioguide_id_validated} to upstream DB.")
                                store_success_count = 0
                                for office in offices:
                                    office_data_full = office.copy()
                                    office_data_full["bioguide_id"] = bioguide_id_validated
                                    if store_district_office(office_data_full, server_instance.database_uri):
                                        store_success_count +=1
                                if store_success_count > 0:
                                    log.info(f"Successfully stored {store_success_count} district offices for {bioguide_id_validated} to upstream.")
                                elif offices: # Only log error if there were offices to store
                                    log.error(f"Failed to store any district offices for {bioguide_id_validated} to upstream.")

                        else:
                            log.error(f"Could not retrieve data for {bioguide_id_validated} to save validation status.")

                        # Send success response to the tab that submitted
                        self.send_response(200)
                        self.send_header('Content-type', 'text/html')
                        self.send_header('Access-Control-Allow-Origin', '*') # Good for local dev
                        self.end_headers()
                        
                        response_html = f"""
                        <!DOCTYPE html><html><head><title>Validation Submitted</title>
                        <style>body{{font-family:Arial,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;background-color:#f0f0f0;}}
                        .msg{{text-align:center;padding:2rem;background:white;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1);}}
                        .s{{color:#4CAF50;}} .r{{color:#f44336;}}</style></head>
                        <body><div class="msg">
                        <h2 class="{'s' if is_valid else 'r'}">Validation for {bioguide_id_validated} {'Accepted' if is_valid else 'Rejected'}</h2>
                        <p>This tab can be closed. The next item (if any) is opening in a new tab.</p>
                        </div></body></html>
                        """
                        self.wfile.write(response_html.encode())

                        # Advance to the next item and trigger its processing
                        server_instance.current_item_index += 1
                        server_instance._process_next_item()
                        
                    else:
                        self.send_error(400, "Invalid decision or bioguide_id parameter")
                else:
                    # Serve files normally if not the /validate path (e.g. if temp_dir had other files)
                    super().do_GET()
            
            def log_message(self, format, *args):
                # Suppress default request logging to keep console cleaner
                # log.debug(f"HTTP Request: {format % args}") # Optionally log to debug
                pass
        
        self.server = HTTPServer(('localhost', self.port), ValidationHandler)
        self.port = self.server.server_port # Update port if auto-selected
        
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True # Allows main program to exit even if thread is running
        self.server_thread.start()
        
        log.info(f"Validation server started on http://localhost:{self.port}")
        
        # Process the first item
        if self.pending_bioguides:
            self._process_next_item()
        else:
            log.info("No pending items to validate.")
            # self.stop() # Optionally stop if queue is empty from start

    def stop(self):
        """Stop the validation server and clean up."""
        if self.server:
            self.server.shutdown() # Signal server to stop
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=5.0) # Wait for thread to finish
            log.info("Validation server stopped.")
            
        if os.path.exists(self.temp_dir):
            import shutil
            try:
                shutil.rmtree(self.temp_dir)
            except Exception as e:
                log.error(f"Error removing temp directory {self.temp_dir}: {e}")
        self.server = None
        self.server_thread = None
