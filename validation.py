#!/usr/bin/env python3

import logging
import os
import sys
import json
import time
import shutil
from typing import Dict, List, Optional, Any, Tuple
import webbrowser
import tempfile

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

class ValidationInterface:
    """Class for handling human validation of extracted district office information."""
    
    def __init__(self):
        """Initialize the validation interface."""
        # Create directories for validated and rejected data
        self.validated_dir = os.path.join(os.path.dirname(__file__), "data", "validated")
        self.rejected_dir = os.path.join(os.path.dirname(__file__), "data", "rejected")
        os.makedirs(self.validated_dir, exist_ok=True)
        os.makedirs(self.rejected_dir, exist_ok=True)
    
    def generate_validation_html(
        self, 
        bioguide_id: str, 
        html_content: str, 
        extracted_offices: List[Dict[str, Any]],
        url: str
    ) -> str:
        """Generate an HTML page for validation.
        
        Args:
            bioguide_id: The bioguide ID being processed
            html_content: The HTML content from the representative's page
            extracted_offices: The extracted office information
            url: The URL that was scraped
            
        Returns:
            Path to the generated HTML file
        """
        # Create a temporary HTML file for validation
        temp_dir = tempfile.mkdtemp()
        html_path = os.path.join(temp_dir, f"{bioguide_id}_validation.html")
        
        # Format the office information as HTML
        offices_html = ""
        for i, office in enumerate(extracted_offices, 1):
            offices_html += f"<div class='office'><h3>Office #{i}</h3>"
            offices_html += "<table>"
            
            # Add each field
            for field in ["office_type", "building", "address", "suite", "city", "state", "zip", "phone", "fax", "hours"]:
                if field in office:
                    offices_html += f"<tr><td><strong>{field.capitalize()}</strong></td><td>{office[field]}</td></tr>"
            
            offices_html += "</table></div>"
        
        # If no offices were found
        if not extracted_offices:
            offices_html = "<p>No district offices were found.</p>"
        
        # Create the validation HTML
        validation_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Validation - {bioguide_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
                .container {{ display: flex; }}
                .left-panel {{ flex: 1; padding-right: 20px; }}
                .right-panel {{ flex: 1; border-left: 1px solid #ccc; padding-left: 20px; }}
                .office {{ margin-bottom: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; }}
                table {{ width: 100%; border-collapse: collapse; }}
                td {{ padding: 5px; border-bottom: 1px solid #eee; }}
                h2 {{ color: #2c3e50; }}
                iframe {{ width: 100%; height: 500px; border: 1px solid #ddd; }}
                .note {{ background-color: #f8f9fa; padding: 10px; border-left: 4px solid #007bff; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h1>District Office Validation - {bioguide_id}</h1>
            <p><strong>Source URL:</strong> <a href="{url}" target="_blank">{url}</a></p>
            
            <div class="note">
                <p><strong>Note:</strong> Please review the extracted information in the left panel and compare with the original HTML in the right panel. 
                Then return to the command line to confirm if the information is correct.</p>
            </div>
            
            <div class="container">
                <div class="left-panel">
                    <h2>Extracted Office Information</h2>
                    {offices_html}
                </div>
                
                <div class="right-panel">
                    <h2>Original Page Content</h2>
                    <iframe srcdoc='{html_content.replace("'", "&apos;")}' title="Original HTML"></iframe>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Write the HTML to the file
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(validation_html)
        
        log.info(f"Generated validation HTML at {html_path}")
        return html_path
    
    def open_validation_interface(self, validation_html_path: str) -> None:
        """Open the validation interface in a web browser.
        
        Args:
            validation_html_path: Path to the validation HTML file
        """
        try:
            url = f"file://{os.path.abspath(validation_html_path)}"
            log.info(f"Opening validation interface at {url}")
            
            # Open the browser with the HTML file
            webbrowser.open(url)
            
        except Exception as e:
            log.error(f"Failed to open validation interface: {e}")
    
    def validate_office_data(
        self, 
        bioguide_id: str, 
        offices: List[Dict[str, Any]], 
        html_content: str,
        url: str
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]]]:
        """Validate the extracted office data through human review.
        
        Args:
            bioguide_id: The bioguide ID being processed
            offices: The extracted office information
            html_content: The HTML content from the representative's page
            url: The URL that was scraped
            
        Returns:
            Tuple of (is_validated, validated_offices)
        """
        # Generate the validation HTML
        validation_html_path = self.generate_validation_html(bioguide_id, html_content, offices, url)
        
        # Open the validation interface in browser
        self.open_validation_interface(validation_html_path)
        
        # Prompt for validation in the command line
        print("\nA browser window should have opened with the validation interface.")
        print(f"Please review the district office information for {bioguide_id}.")
        
        # Get user input
        is_valid = None
        while is_valid is None:
            response = input("Is the extracted information correct? (Y/n): ").strip().lower()
            if response == "" or response == "y":
                is_valid = True
            elif response == "n":
                is_valid = False
            else:
                print("Please enter 'Y' or 'n'")
        
        if is_valid:
            log.info(f"User approved office data for {bioguide_id}")
            
            # Save the validated data
            self._save_validated_data(bioguide_id, offices, html_content, url)
            
            return True, offices
        else:
            log.info(f"User rejected office data for {bioguide_id}")
            
            # Save the rejected data
            self._save_rejected_data(bioguide_id, offices, html_content, url)
            
            return False, None
    
    def _save_validated_data(
        self, 
        bioguide_id: str, 
        offices: List[Dict[str, Any]], 
        html_content: str,
        url: str
    ) -> None:
        """Save validated data.
        
        Args:
            bioguide_id: The bioguide ID being processed
            offices: The extracted office information
            html_content: The HTML content from the representative's page
            url: The URL that was scraped
        """
        timestamp = int(time.time())
        data_dir = os.path.join(self.validated_dir, bioguide_id)
        os.makedirs(data_dir, exist_ok=True)
        
        # Save the office data
        with open(os.path.join(data_dir, f"{timestamp}_offices.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "bioguide_id": bioguide_id,
                "url": url,
                "offices": offices,
                "validation_timestamp": timestamp,
                "validation_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2)
        
        # Save the HTML content
        with open(os.path.join(data_dir, f"{timestamp}_source.html"), 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        log.info(f"Saved validated data for {bioguide_id}")
    
    def _save_rejected_data(
        self, 
        bioguide_id: str, 
        offices: List[Dict[str, Any]], 
        html_content: str,
        url: str
    ) -> None:
        """Save rejected data.
        
        Args:
            bioguide_id: The bioguide ID being processed
            offices: The extracted office information
            html_content: The HTML content from the representative's page
            url: The URL that was scraped
        """
        timestamp = int(time.time())
        data_dir = os.path.join(self.rejected_dir, bioguide_id)
        os.makedirs(data_dir, exist_ok=True)
        
        # Save the office data
        with open(os.path.join(data_dir, f"{timestamp}_offices.json"), 'w', encoding='utf-8') as f:
            json.dump({
                "bioguide_id": bioguide_id,
                "url": url,
                "offices": offices,
                "rejection_timestamp": timestamp,
                "rejection_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }, f, indent=2)
        
        # Save the HTML content
        with open(os.path.join(data_dir, f"{timestamp}_source.html"), 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        log.info(f"Saved rejected data for {bioguide_id}")