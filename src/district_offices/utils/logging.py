#!/usr/bin/env python3

import logging
import os
import sys
import json
import time
import shutil
from typing import Dict, Any, Optional, List
import uuid

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

# Lazy import to avoid circular imports
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

class ProvenanceTracker:
    """Class for tracking provenance of district office data using SQLite."""
    
    def __init__(self):
        """Initialize the provenance tracker."""
        # Generate a unique run ID
        self.run_id = str(uuid.uuid4())
        self.run_timestamp = int(time.time())
        self.run_date = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Get database instance
        self.db = _get_sqlite_db()
        
        # Track current processes
        self.current_processes = {}  # bioguide_id -> extraction_id mapping
        
        log.info(f"Initialized ProvenanceTracker with run ID: {self.run_id}")
    
    def log_process_start(self, bioguide_id: str) -> str:
        """Log the start of processing for a bioguide ID.
        
        Args:
            bioguide_id: The bioguide ID being processed
            
        Returns:
            String identifier for this process (format: "extraction:{id}")
        """
        # Create extraction record in database
        extraction = self.db.create_extraction(bioguide_id, source_url=None)
        extraction_id = extraction.id
        
        # Store mapping
        self.current_processes[bioguide_id] = extraction_id
        
        # Create provenance log entry
        log_data = {
            "run_id": self.run_id,
            "start_timestamp": int(time.time()),
            "start_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "started"
        }
        
        self.db.create_provenance_log(
            extraction_id=extraction_id,
            event_type="process_start",
            event_data=log_data
        )
        
        log.info(f"Started processing for {bioguide_id} (extraction_id: {extraction_id})")
        return f"extraction:{extraction_id}"
    
    def log_step(self, log_path: str, step_name: str, step_data: Dict[str, Any]) -> None:
        """Log a step in the processing of a bioguide ID.
        
        Args:
            log_path: Process identifier (format: "extraction:{id}")
            step_name: Name of the step
            step_data: Data for the step
        """
        try:
            # Extract extraction_id from log_path
            if log_path.startswith("extraction:"):
                extraction_id = int(log_path.split(":")[1])
            else:
                # Legacy format - try to find from current processes
                for bid, eid in self.current_processes.items():
                    if log_path.endswith(bid):
                        extraction_id = eid
                        break
                else:
                    log.warning(f"Could not find extraction_id for log_path: {log_path}")
                    return
            
            # Create provenance log entry
            log_data = {
                "step_name": step_name,
                "timestamp": int(time.time()),
                "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "data": step_data
            }
            
            self.db.create_provenance_log(
                extraction_id=extraction_id,
                event_type=f"step_{step_name}",
                event_data=log_data
            )
            
            log.info(f"Logged step {step_name} for extraction {extraction_id}")
        except Exception as e:
            log.error(f"Failed to log step: {e}")
    
    def save_artifact(self, log_path: str, artifact_name: str, content: str, file_extension: str = "txt") -> str:
        """Save an artifact (HTML, JSON, etc.) for a bioguide ID.
        
        Args:
            log_path: Process identifier (format: "extraction:{id}")
            artifact_name: Name of the artifact
            content: Content of the artifact
            file_extension: File extension for the artifact
            
        Returns:
            Artifact identifier (format: "artifact:{id}")
        """
        try:
            # Extract extraction_id
            if log_path.startswith("extraction:"):
                extraction_id = int(log_path.split(":")[1])
            else:
                log.warning(f"Invalid log_path format: {log_path}")
                return ""
            
            # Determine content type
            content_type_map = {
                'html': 'text/html',
                'json': 'application/json',
                'txt': 'text/plain',
                'xml': 'application/xml'
            }
            content_type = content_type_map.get(file_extension, 'application/octet-stream')
            
            # Store artifact
            artifact_id = self.db.store_artifact(
                extraction_id=extraction_id,
                artifact_type=artifact_name,
                filename=f"{artifact_name}_{int(time.time())}.{file_extension}",
                content=content.encode('utf-8'),
                content_type=content_type
            )
            
            # Log the artifact creation
            self.log_step(log_path, f"save_{artifact_name}", {
                "artifact_id": artifact_id,
                "artifact_type": artifact_name,
                "file_extension": file_extension,
                "size": len(content)
            })
            
            log.info(f"Saved artifact {artifact_name} (ID: {artifact_id}) for extraction {extraction_id}")
            return f"artifact:{artifact_id}"
            
        except Exception as e:
            log.error(f"Failed to save artifact: {e}")
            return ""
    
    def save_json_artifact(self, log_path: str, artifact_name: str, data: Dict[str, Any]) -> str:
        """Save a JSON artifact for a bioguide ID.
        
        Args:
            log_path: Process identifier (format: "extraction:{id}")
            artifact_name: Name of the artifact
            data: Dictionary to save as JSON
            
        Returns:
            Artifact identifier (format: "artifact:{id}")
        """
        json_content = json.dumps(data, indent=2)
        return self.save_artifact(log_path, artifact_name, json_content, "json")
    
    def log_validation_artifacts(
        self, 
        log_path: str, 
        validation_html_path: str, 
        extracted_offices: List[Dict[str, Any]],
        is_valid: bool
    ) -> None:
        """Log validation artifacts (HTML and JSON).
        
        Args:
            log_path: Process identifier (format: "extraction:{id}")
            validation_html_path: Path to the validation HTML file
            extracted_offices: List of extracted offices
            is_valid: Whether the extraction was validated
        """
        try:
            # Extract extraction_id
            if log_path.startswith("extraction:"):
                extraction_id = int(log_path.split(":")[1])
            else:
                log.warning(f"Invalid log_path format: {log_path}")
                return
            
            # Read validation HTML if it's a file path
            if os.path.exists(validation_html_path):
                with open(validation_html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # Store validation HTML
                self.save_artifact(log_path, "validation_html", html_content, "html")
            
            # Store offices JSON
            validation_data = {
                "offices": extracted_offices,
                "is_valid": is_valid,
                "validation_timestamp": int(time.time()),
                "validation_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.save_json_artifact(log_path, "validation_result", validation_data)
            
            # Update extraction status
            status = "validated" if is_valid else "rejected"
            self.db.update_extraction_status(extraction_id, status)
            
            log.info(f"Logged validation artifacts for extraction {extraction_id} (valid: {is_valid})")
            
        except Exception as e:
            log.error(f"Failed to log validation artifacts: {e}")
    
    def log_process_end(self, log_path: str, status: str, message: Optional[str] = None) -> None:
        """Log the end of processing for a bioguide ID.
        
        Args:
            log_path: Process identifier (format: "extraction:{id}")
            status: Status of the processing (completed, failed, skipped, stored)
            message: Optional message
        """
        try:
            # Extract extraction_id
            if log_path.startswith("extraction:"):
                extraction_id = int(log_path.split(":")[1])
            else:
                log.warning(f"Invalid log_path format: {log_path}")
                return
            
            # Create final provenance log entry
            log_data = {
                "run_id": self.run_id,
                "end_timestamp": int(time.time()),
                "end_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "status": status,
                "message": message
            }
            
            self.db.create_provenance_log(
                extraction_id=extraction_id,
                event_type="process_end",
                event_data=log_data
            )
            
            # Update extraction status if needed
            if status in ["failed", "completed"]:
                self.db.update_extraction_status(extraction_id, status)
            
            # Remove from current processes
            bioguide_id = None
            for bid, eid in list(self.current_processes.items()):
                if eid == extraction_id:
                    bioguide_id = bid
                    del self.current_processes[bid]
                    break
            
            log.info(f"Completed processing for extraction {extraction_id} with status: {status}")
            
        except Exception as e:
            log.error(f"Failed to log process end: {e}")
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of the run.
        
        Returns:
            Summary dictionary
        """
        try:
            # Query database for run statistics
            with self.db.get_session() as session:
                from district_offices.storage.models import Extraction, ProvenanceLog
                
                # Find all extractions from this run
                run_extractions = session.query(Extraction).join(ProvenanceLog).filter(
                    ProvenanceLog.event_type == "process_start",
                    ProvenanceLog.event_data.contains(f'"run_id": "{self.run_id}"')
                ).all()
                
                # Count by status
                status_counts = {
                    "pending": 0,
                    "processing": 0,
                    "validated": 0,
                    "rejected": 0,
                    "failed": 0,
                    "completed": 0
                }
                
                for extraction in run_extractions:
                    status = extraction.status
                    if status in status_counts:
                        status_counts[status] += 1
                
                # Generate summary
                summary = {
                    "run_id": self.run_id,
                    "run_date": self.run_date,
                    "total_processed": len(run_extractions),
                    "total_validated": status_counts["validated"],
                    "total_rejected": status_counts["rejected"],
                    "total_failed": status_counts["failed"],
                    "total_pending": status_counts["pending"],
                    "duration_seconds": int(time.time()) - self.run_timestamp
                }
                
                log.info(f"Generated summary for run {self.run_id}: {summary}")
                return summary
                
        except Exception as e:
            log.error(f"Failed to generate summary: {e}")
            return {
                "run_id": self.run_id,
                "error": str(e)
            }