#!/usr/bin/env python3

import logging
import os
import json
import time
import shutil
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

class ExtractionStatus(Enum):
    """Status of an extraction in the staging system."""
    PENDING = "pending"
    VALIDATED = "validated"
    REJECTED = "rejected"
    FAILED = "failed"

@dataclass
class ExtractionData:
    """Data container for a staged extraction."""
    bioguide_id: str
    status: ExtractionStatus
    extraction_timestamp: int
    validation_timestamp: Optional[int]
    source_url: str
    extracted_offices: List[Dict[str, Any]]
    artifacts: Dict[str, str]  # artifact_name -> file_path
    provenance_log: str
    metadata: Dict[str, Any]

class StagingManager:
    """Manages the staging directory for async extraction and validation."""
    
    def __init__(self, staging_dir: Optional[str] = None):
        """Initialize the staging manager.
        
        Args:
            staging_dir: Custom staging directory path. If None, uses default.
        """
        if staging_dir:
            self.staging_root = staging_dir
        else:
            # Get project root directory (load_reps_sites)
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            self.staging_root = os.path.join(project_root, "data", "staging")
        
        # Create staging subdirectories
        self.pending_dir = os.path.join(self.staging_root, "pending")
        self.validated_dir = os.path.join(self.staging_root, "validated")
        self.rejected_dir = os.path.join(self.staging_root, "rejected")
        self.failed_dir = os.path.join(self.staging_root, "failed")
        
        # Create directories if they don't exist
        for directory in [self.pending_dir, self.validated_dir, self.rejected_dir, self.failed_dir]:
            os.makedirs(directory, exist_ok=True)
        
        # Queue file for tracking extractions
        self.queue_file = os.path.join(self.staging_root, "queue.json")
        self._initialize_queue()
    
    def _initialize_queue(self) -> None:
        """Initialize the queue file if it doesn't exist."""
        if not os.path.exists(self.queue_file):
            queue_data = {
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "extractions": {}
            }
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, indent=2)
    
    def _update_queue(self, bioguide_id: str, status: ExtractionStatus, staging_path: str) -> None:
        """Update the queue with extraction status.
        
        Args:
            bioguide_id: The bioguide ID
            status: Current status of the extraction
            staging_path: Path to the staged extraction data
        """
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            queue_data["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            queue_data["extractions"][bioguide_id] = {
                "status": status.value,
                "staging_path": staging_path,
                "last_updated": int(time.time())
            }
            
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, indent=2)
                
        except Exception as e:
            log.error(f"Failed to update queue: {e}")
    
    def save_extraction(
        self,
        bioguide_id: str,
        source_url: str,
        extracted_offices: List[Dict[str, Any]],
        artifacts: Dict[str, str],
        provenance_log: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save an extraction to staging.
        
        Args:
            bioguide_id: The bioguide ID
            source_url: URL that was scraped
            extracted_offices: Extracted office data
            artifacts: Dictionary of artifact names to file paths
            provenance_log: Path to the provenance log
            metadata: Additional metadata
            
        Returns:
            Path to the staged extraction directory
        """
        timestamp = int(time.time())
        extraction_dir = os.path.join(self.pending_dir, f"{bioguide_id}_{timestamp}")
        os.makedirs(extraction_dir, exist_ok=True)
        
        # Copy artifacts to staging directory
        staged_artifacts = {}
        for artifact_name, artifact_path in artifacts.items():
            if os.path.exists(artifact_path):
                staged_artifact_path = os.path.join(extraction_dir, f"{artifact_name}.{self._get_file_extension(artifact_path)}")
                shutil.copy2(artifact_path, staged_artifact_path)
                staged_artifacts[artifact_name] = staged_artifact_path
            else:
                log.warning(f"Artifact not found: {artifact_path}")
        
        # Copy provenance log
        staged_provenance_log = os.path.join(extraction_dir, "provenance.json")
        if os.path.exists(provenance_log):
            shutil.copy2(provenance_log, staged_provenance_log)
        else:
            log.warning(f"Provenance log not found: {provenance_log}")
        
        # Create extraction metadata
        extraction_metadata = {
            "bioguide_id": bioguide_id,
            "status": ExtractionStatus.PENDING.value,
            "extraction_timestamp": timestamp,
            "extraction_date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
            "validation_timestamp": None,
            "source_url": source_url,
            "extracted_offices": extracted_offices,
            "artifacts": staged_artifacts,
            "provenance_log": staged_provenance_log,
            "metadata": metadata or {}
        }
        
        # Save metadata
        metadata_path = os.path.join(extraction_dir, "extraction.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(extraction_metadata, f, indent=2)
        
        # Update queue
        self._update_queue(bioguide_id, ExtractionStatus.PENDING, extraction_dir)
        
        log.info(f"Saved extraction for {bioguide_id} to staging: {extraction_dir}")
        return extraction_dir
    
    def _get_file_extension(self, file_path: str) -> str:
        """Get file extension from path."""
        _, ext = os.path.splitext(file_path)
        return ext.lstrip('.') or 'txt'
    
    def load_pending_extractions(self) -> List[str]:
        """Load all pending extractions.
        
        Returns:
            List of bioguide IDs with pending extractions
        """
        pending_bioguides = []
        
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            for bioguide_id, extraction_info in queue_data["extractions"].items():
                if extraction_info["status"] == ExtractionStatus.PENDING.value:
                    pending_bioguides.append(bioguide_id)
                    
        except Exception as e:
            log.error(f"Failed to load pending extractions: {e}")
        
        return pending_bioguides
    
    def load_all_extractions(self) -> List[str]:
        """Load all extractions regardless of status.
        
        Returns:
            List of all bioguide IDs in staging
        """
        all_bioguides = []
        
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            all_bioguides = list(queue_data["extractions"].keys())
                    
        except Exception as e:
            log.error(f"Failed to load all extractions: {e}")
        
        return all_bioguides
    
    def get_extraction_data(self, bioguide_id: str) -> Optional[ExtractionData]:
        """Get extraction data for a bioguide ID.
        
        Args:
            bioguide_id: The bioguide ID
            
        Returns:
            ExtractionData object or None if not found
        """
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            if bioguide_id not in queue_data["extractions"]:
                return None
            
            extraction_info = queue_data["extractions"][bioguide_id]
            staging_path = extraction_info["staging_path"]
            
            # Load extraction metadata
            metadata_path = os.path.join(staging_path, "extraction.json")
            if not os.path.exists(metadata_path):
                log.error(f"Extraction metadata not found: {metadata_path}")
                return None
            
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            return ExtractionData(
                bioguide_id=metadata["bioguide_id"],
                status=ExtractionStatus(metadata["status"]),
                extraction_timestamp=metadata["extraction_timestamp"],
                validation_timestamp=metadata.get("validation_timestamp"),
                source_url=metadata["source_url"],
                extracted_offices=metadata["extracted_offices"],
                artifacts=metadata["artifacts"],
                provenance_log=metadata["provenance_log"],
                metadata=metadata.get("metadata", {})
            )
            
        except Exception as e:
            log.error(f"Failed to get extraction data for {bioguide_id}: {e}")
            return None
    
    def mark_validated(self, bioguide_id: str, approved: bool) -> bool:
        """Mark an extraction as validated or rejected.
        
        Args:
            bioguide_id: The bioguide ID
            approved: Whether the extraction was approved
            
        Returns:
            True if successful, False otherwise
        """
        extraction_data = self.get_extraction_data(bioguide_id)
        if not extraction_data:
            log.error(f"Extraction data not found for {bioguide_id}")
            return False
        
        try:
            # Determine new status and destination directory
            if approved:
                new_status = ExtractionStatus.VALIDATED
                dest_dir = self.validated_dir
            else:
                new_status = ExtractionStatus.REJECTED
                dest_dir = self.rejected_dir
            
            # Get current staging path
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            current_path = queue_data["extractions"][bioguide_id]["staging_path"]
            
            # Move to appropriate directory
            timestamp = int(time.time())
            new_path = os.path.join(dest_dir, f"{bioguide_id}_{timestamp}")
            shutil.move(current_path, new_path)
            
            # Update metadata
            metadata_path = os.path.join(new_path, "extraction.json")
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            
            metadata["status"] = new_status.value
            metadata["validation_timestamp"] = timestamp
            metadata["validation_date"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
            
            # Update artifact paths
            for artifact_name, old_path in metadata["artifacts"].items():
                relative_path = os.path.relpath(old_path, current_path)
                metadata["artifacts"][artifact_name] = os.path.join(new_path, relative_path)
            
            # Update provenance log path
            relative_provenance = os.path.relpath(metadata["provenance_log"], current_path)
            metadata["provenance_log"] = os.path.join(new_path, relative_provenance)
            
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            # Update queue
            self._update_queue(bioguide_id, new_status, new_path)
            
            log.info(f"Marked {bioguide_id} as {new_status.value}: {new_path}")
            return True
            
        except Exception as e:
            log.error(f"Failed to mark {bioguide_id} as validated: {e}")
            return False
    
    def mark_failed(self, bioguide_id: str, error_message: str) -> bool:
        """Mark an extraction as failed.
        
        Args:
            bioguide_id: The bioguide ID
            error_message: Error message describing the failure
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Create failed extraction directory
            timestamp = int(time.time())
            failed_path = os.path.join(self.failed_dir, f"{bioguide_id}_{timestamp}")
            os.makedirs(failed_path, exist_ok=True)
            
            # Create failure metadata
            failure_metadata = {
                "bioguide_id": bioguide_id,
                "status": ExtractionStatus.FAILED.value,
                "extraction_timestamp": timestamp,
                "extraction_date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp)),
                "error_message": error_message,
                "metadata": {}
            }
            
            # Save metadata
            metadata_path = os.path.join(failed_path, "extraction.json")
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(failure_metadata, f, indent=2)
            
            # Update queue
            self._update_queue(bioguide_id, ExtractionStatus.FAILED, failed_path)
            
            log.info(f"Marked {bioguide_id} as failed: {error_message}")
            return True
            
        except Exception as e:
            log.error(f"Failed to mark {bioguide_id} as failed: {e}")
            return False
    
    def cleanup_processed(self, older_than_days: int = 30) -> Tuple[int, int]:
        """Clean up processed extractions older than specified days.
        
        Args:
            older_than_days: Remove extractions older than this many days
            
        Returns:
            Tuple of (removed_count, total_size_freed)
        """
        cutoff_timestamp = time.time() - (older_than_days * 24 * 60 * 60)
        removed_count = 0
        total_size_freed = 0
        
        # Clean validated and rejected directories
        for directory in [self.validated_dir, self.rejected_dir, self.failed_dir]:
            if not os.path.exists(directory):
                continue
                
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isdir(item_path):
                    # Get creation time from metadata
                    metadata_path = os.path.join(item_path, "extraction.json")
                    if os.path.exists(metadata_path):
                        try:
                            with open(metadata_path, 'r', encoding='utf-8') as f:
                                metadata = json.load(f)
                            
                            extraction_timestamp = metadata.get("extraction_timestamp", 0)
                            if extraction_timestamp < cutoff_timestamp:
                                # Calculate size before removal
                                size_freed = self._get_directory_size(item_path)
                                
                                # Remove directory
                                shutil.rmtree(item_path)
                                removed_count += 1
                                total_size_freed += size_freed
                                
                                log.info(f"Removed old extraction: {item_path}")
                                
                        except Exception as e:
                            log.error(f"Failed to process {item_path}: {e}")
        
        # Update queue by removing cleaned entries
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            # Remove entries for cleaned extractions
            updated_extractions = {}
            for bioguide_id, extraction_info in queue_data["extractions"].items():
                staging_path = extraction_info["staging_path"]
                if os.path.exists(staging_path):
                    updated_extractions[bioguide_id] = extraction_info
            
            queue_data["extractions"] = updated_extractions
            queue_data["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
            
            with open(self.queue_file, 'w', encoding='utf-8') as f:
                json.dump(queue_data, f, indent=2)
                
        except Exception as e:
            log.error(f"Failed to update queue after cleanup: {e}")
        
        log.info(f"Cleanup complete: removed {removed_count} extractions, freed {total_size_freed:,} bytes")
        return removed_count, total_size_freed
    
    def _get_directory_size(self, directory: str) -> int:
        """Get the total size of a directory in bytes."""
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                file_path = os.path.join(dirpath, filename)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
        return total_size
    
    def get_staging_summary(self) -> Dict[str, Any]:
        """Get a summary of the staging system.
        
        Returns:
            Dictionary with staging statistics
        """
        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                queue_data = json.load(f)
            
            status_counts = {}
            for status in ExtractionStatus:
                status_counts[status.value] = 0
            
            for extraction_info in queue_data["extractions"].values():
                status = extraction_info["status"]
                if status in status_counts:
                    status_counts[status] += 1
            
            return {
                "total_extractions": len(queue_data["extractions"]),
                "status_counts": status_counts,
                "queue_created": queue_data.get("created"),
                "last_updated": queue_data.get("last_updated"),
                "staging_root": self.staging_root
            }
            
        except Exception as e:
            log.error(f"Failed to get staging summary: {e}")
            return {}