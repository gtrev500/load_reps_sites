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

class ProvenanceTracker:
    """Class for tracking provenance of district office data."""
    
    def __init__(self):
        """Initialize the provenance tracker."""
        # Create directories for provenance logs and artifacts
        self.logs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "provenance")
        self.runs_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "runs")
        self.artifacts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "logs", "artifacts")
        
        os.makedirs(self.logs_dir, exist_ok=True)
        os.makedirs(self.runs_dir, exist_ok=True)
        os.makedirs(self.artifacts_dir, exist_ok=True)
        
        # Generate a unique run ID
        self.run_id = str(uuid.uuid4())
        self.run_timestamp = int(time.time())
        self.run_date = time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Initialize the run log
        self._initialize_run_log()
    
    def _initialize_run_log(self):
        """Initialize the run log."""
        run_log = {
            "run_id": self.run_id,
            "timestamp": self.run_timestamp,
            "date": self.run_date,
            "processed_bioguides": [],
            "validated_bioguides": [],
            "stored_bioguides": [],
            "skipped_bioguides": [],
            "failed_bioguides": []
        }
        
        # Write the run log
        run_log_path = os.path.join(self.runs_dir, f"run_{self.run_id}.json")
        with open(run_log_path, 'w', encoding='utf-8') as f:
            json.dump(run_log, f, indent=2)
        
        log.info(f"Initialized run log with ID: {self.run_id}")
    
    def log_process_start(self, bioguide_id: str) -> str:
        """Log the start of processing for a bioguide ID.
        
        Args:
            bioguide_id: The bioguide ID being processed
            
        Returns:
            Path to the provenance log file
        """
        process_id = f"{bioguide_id}_{self.run_timestamp}"
        log_path = os.path.join(self.logs_dir, f"{process_id}.json")
        
        # Create a dedicated artifacts directory for this bioguide ID
        bioguide_artifacts_dir = os.path.join(self.artifacts_dir, bioguide_id, str(self.run_timestamp))
        os.makedirs(bioguide_artifacts_dir, exist_ok=True)
        
        provenance_log = {
            "process_id": process_id,
            "run_id": self.run_id,
            "bioguide_id": bioguide_id,
            "start_timestamp": int(time.time()),
            "start_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": "started",
            "artifacts_directory": bioguide_artifacts_dir,
            "steps": []
        }
        
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(provenance_log, f, indent=2)
        
        # Update the run log
        self._update_run_log("processed_bioguides", bioguide_id)
        
        log.info(f"Started processing for {bioguide_id}")
        return log_path
    
    def log_step(self, log_path: str, step_name: str, step_data: Dict[str, Any]) -> None:
        """Log a step in the processing of a bioguide ID.
        
        Args:
            log_path: Path to the provenance log file
            step_name: Name of the step
            step_data: Data for the step
        """
        try:
            # Read the existing log
            with open(log_path, 'r', encoding='utf-8') as f:
                provenance_log = json.load(f)
            
            # Add the step
            step = {
                "step_name": step_name,
                "timestamp": int(time.time()),
                "date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "data": step_data
            }
            
            provenance_log["steps"].append(step)
            
            # Write the updated log
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(provenance_log, f, indent=2)
            
            log.info(f"Logged step {step_name} for {provenance_log['bioguide_id']}")
        except Exception as e:
            log.error(f"Failed to log step: {e}")
    
    def save_artifact(self, log_path: str, artifact_name: str, content: str, file_extension: str = "txt") -> str:
        """Save an artifact (HTML, JSON, etc.) for a bioguide ID.
        
        Args:
            log_path: Path to the provenance log file
            artifact_name: Name of the artifact
            content: Content of the artifact
            file_extension: File extension for the artifact
            
        Returns:
            Path to the saved artifact
        """
        try:
            # Read the existing log
            with open(log_path, 'r', encoding='utf-8') as f:
                provenance_log = json.load(f)
            
            # Get the artifacts directory
            artifacts_dir = provenance_log["artifacts_directory"]
            
            # Create the artifact file
            timestamp = int(time.time())
            artifact_path = os.path.join(artifacts_dir, f"{artifact_name}_{timestamp}.{file_extension}")
            
            # Save the artifact
            with open(artifact_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Add a reference to the artifact in the log
            step_data = {
                "artifact_name": artifact_name,
                "artifact_path": artifact_path,
                "file_extension": file_extension
            }
            
            self.log_step(log_path, f"save_{artifact_name}", step_data)
            
            log.info(f"Saved artifact {artifact_name} for {provenance_log['bioguide_id']}")
            return artifact_path
        except Exception as e:
            log.error(f"Failed to save artifact: {e}")
            return ""
    
    def save_json_artifact(self, log_path: str, artifact_name: str, data: Dict[str, Any]) -> str:
        """Save a JSON artifact for a bioguide ID.
        
        Args:
            log_path: Path to the provenance log file
            artifact_name: Name of the artifact
            data: Dictionary to save as JSON
            
        Returns:
            Path to the saved artifact
        """
        try:
            # Read the existing log
            with open(log_path, 'r', encoding='utf-8') as f:
                provenance_log = json.load(f)
            
            # Get the artifacts directory
            artifacts_dir = provenance_log["artifacts_directory"]
            
            # Create the artifact file
            timestamp = int(time.time())
            artifact_path = os.path.join(artifacts_dir, f"{artifact_name}_{timestamp}.json")
            
            # Save the artifact
            with open(artifact_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            # Add a reference to the artifact in the log
            step_data = {
                "artifact_name": artifact_name,
                "artifact_path": artifact_path,
                "file_extension": "json"
            }
            
            self.log_step(log_path, f"save_{artifact_name}", step_data)
            
            log.info(f"Saved JSON artifact {artifact_name} for {provenance_log['bioguide_id']}")
            return artifact_path
        except Exception as e:
            log.error(f"Failed to save JSON artifact: {e}")
            return ""
    
    def log_validation_artifacts(
        self, 
        log_path: str, 
        validation_html_path: str, 
        extracted_offices: List[Dict[str, Any]],
        is_valid: bool
    ) -> None:
        """Log validation artifacts (HTML and JSON).
        
        Args:
            log_path: Path to the provenance log file
            validation_html_path: Path to the validation HTML file
            extracted_offices: List of extracted offices
            is_valid: Whether the extraction was validated
        """
        try:
            # Read the existing log
            with open(log_path, 'r', encoding='utf-8') as f:
                provenance_log = json.load(f)
            
            # Get the artifacts directory
            artifacts_dir = provenance_log["artifacts_directory"]
            
            # Copy the validation HTML to the artifacts directory
            timestamp = int(time.time())
            html_artifact_path = os.path.join(artifacts_dir, f"validation_html_{timestamp}.html")
            
            shutil.copy2(validation_html_path, html_artifact_path)
            
            # Save the offices JSON
            json_artifact_path = os.path.join(artifacts_dir, f"extracted_offices_{timestamp}.json")
            with open(json_artifact_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "bioguide_id": provenance_log["bioguide_id"],
                    "offices": extracted_offices,
                    "is_valid": is_valid,
                    "validation_timestamp": timestamp,
                    "validation_date": time.strftime("%Y-%m-%d %H:%M:%S")
                }, f, indent=2)
            
            # Add a reference to the artifacts in the log
            step_data = {
                "html_artifact_path": html_artifact_path,
                "json_artifact_path": json_artifact_path,
                "is_valid": is_valid
            }
            
            self.log_step(log_path, "validation", step_data)
            
            log.info(f"Logged validation artifacts for {provenance_log['bioguide_id']}")
        except Exception as e:
            log.error(f"Failed to log validation artifacts: {e}")
    
    def log_process_end(self, log_path: str, status: str, message: Optional[str] = None) -> None:
        """Log the end of processing for a bioguide ID.
        
        Args:
            log_path: Path to the provenance log file
            status: Status of the processing (completed, failed, skipped)
            message: Optional message
        """
        try:
            # Read the existing log
            with open(log_path, 'r', encoding='utf-8') as f:
                provenance_log = json.load(f)
            
            # Update the status
            provenance_log["status"] = status
            provenance_log["end_timestamp"] = int(time.time())
            provenance_log["end_date"] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            if message:
                provenance_log["message"] = message
            
            # Write the updated log
            with open(log_path, 'w', encoding='utf-8') as f:
                json.dump(provenance_log, f, indent=2)
            
            # Update the run log
            bioguide_id = provenance_log["bioguide_id"]
            if status == "completed":
                self._update_run_log("validated_bioguides", bioguide_id)
            elif status == "stored":
                self._update_run_log("stored_bioguides", bioguide_id)
            elif status == "skipped":
                self._update_run_log("skipped_bioguides", bioguide_id)
            elif status == "failed":
                self._update_run_log("failed_bioguides", bioguide_id)
            
            log.info(f"Completed processing for {bioguide_id} with status: {status}")
        except Exception as e:
            log.error(f"Failed to log process end: {e}")
    
    def _update_run_log(self, list_name: str, bioguide_id: str) -> None:
        """Update the run log with a bioguide ID.
        
        Args:
            list_name: Name of the list to update
            bioguide_id: The bioguide ID to add
        """
        try:
            run_log_path = os.path.join(self.runs_dir, f"run_{self.run_id}.json")
            
            # Read the existing run log
            with open(run_log_path, 'r', encoding='utf-8') as f:
                run_log = json.load(f)
            
            # Add the bioguide ID to the specified list if not already there
            if bioguide_id not in run_log[list_name]:
                run_log[list_name].append(bioguide_id)
            
            # Write the updated run log
            with open(run_log_path, 'w', encoding='utf-8') as f:
                json.dump(run_log, f, indent=2)
        except Exception as e:
            log.error(f"Failed to update run log: {e}")
    
    def generate_summary(self) -> Dict[str, Any]:
        """Generate a summary of the run.
        
        Returns:
            Summary dictionary
        """
        try:
            run_log_path = os.path.join(self.runs_dir, f"run_{self.run_id}.json")
            
            # Read the run log
            with open(run_log_path, 'r', encoding='utf-8') as f:
                run_log = json.load(f)
            
            # Generate summary
            summary = {
                "run_id": self.run_id,
                "run_date": self.run_date,
                "total_processed": len(run_log["processed_bioguides"]),
                "total_validated": len(run_log["validated_bioguides"]),
                "total_stored": len(run_log["stored_bioguides"]),
                "total_skipped": len(run_log["skipped_bioguides"]),
                "total_failed": len(run_log["failed_bioguides"]),
                "duration_seconds": int(time.time()) - self.run_timestamp
            }
            
            # Write summary to the run log
            run_log["summary"] = summary
            with open(run_log_path, 'w', encoding='utf-8') as f:
                json.dump(run_log, f, indent=2)
            
            log.info(f"Generated summary for run {self.run_id}")
            return summary
        except Exception as e:
            log.error(f"Failed to generate summary: {e}")
            return {}
