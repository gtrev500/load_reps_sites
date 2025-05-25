#!/usr/bin/env python3

import logging
import os
import sys
import json
import time
import shutil
import subprocess
from typing import Dict, List, Optional, Any, Tuple
import webbrowser
import tempfile
import html
from bs4 import BeautifulSoup, Comment, Doctype, CData, NavigableString, Tag

# --- Field Styling Configuration ---
FIELD_COLOR_MAP = {
    "address": "#90EE90",       # lightgreen
    "zip": "#F08080",           # lightcoral
    "phone": "#ADD8E6",         # lightblue
    "city": "#FFD700",          # gold
    "state": "#DA70D6",         # orchid
    "office_type": "#E6E6FA",   # lavender
    "building": "#D2B48C",       # tan
    "suite": "#FFB6C1",         # lightpink
    "fax": "#B0E0E6",           # powderblue
    "hours": "#FAFAD2",         # lightgoldenrodyellow
    "default_highlight": "yellow" # Fallback for general highlights
}

FIELD_HIGHLIGHT_PRIORITY = {
    # Higher priority (processed first for ambiguous strings of same length)
    "zip": 0,
    "phone": 1,
    "fax": 2,
    "state": 3,
    "suite": 4,
    "address": 5, 
    "city": 6,
    # Lower priority
    "hours": 7,
    "building": 8,
    "office_type": 9,
    "default_priority": 99 # Fallback for unlisted fields
}

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

class ValidationInterface:
    """Class for handling human validation of extracted district office information."""
    
    def __init__(self, browser_validation=False):
        """Initialize the validation interface.
        
        Args:
            browser_validation: Whether to use browser-based validation (default: False)
        """
        self.browser_validation = browser_validation
        self.validation_server = None
        self.db = _get_sqlite_db()

    def generate_validation_html(
        self,
        bioguide_id: str,
        html_content: str,
        extracted_offices: List[Dict[str, Any]],
        url: str,
        contact_sections: str
    ) -> str:
        """Generate an HTML page for validation.
        
        Args:
            bioguide_id: The bioguide ID being processed
            html_content: The HTML content from the representative's page
            extracted_offices: The extracted office information
            url: The URL that was scraped
            contact_sections: The HTML sections fed to the LLM
            
        Returns:
            Path to the generated HTML file
        """
        # Create a temporary HTML file for validation
        temp_dir = tempfile.mkdtemp()
        html_path = os.path.join(temp_dir, f"{bioguide_id}_validation.html")

        # --- Highlight LLM output in the original HTML content ---
        soup = BeautifulSoup(html_content, 'html.parser')
        
        field_values_to_highlight = [] # Store (value, field_name) tuples
        for office in extracted_offices:
            for field_name, value in office.items(): # Use field_name (formerly key)
                if isinstance(value, str) and value.strip():
                    field_values_to_highlight.append((value, field_name.lower()))
        
        # Sort by length of value (descending) primarily.
        # For items of the same length, sort by field_name priority (ascending).
        # item[0] is the text value, item[1] is the field_name (already lowercased).
        sorted_field_values = sorted(
            field_values_to_highlight,
            key=lambda item: (
                -len(item[0]),  # Primary sort: length descending (hence negative)
                FIELD_HIGHLIGHT_PRIORITY.get(item[1], FIELD_HIGHLIGHT_PRIORITY["default_priority"])  # Secondary sort: priority ascending
            )
        )

        for text_val, field_name in sorted_field_values: # Iterate with field_name
            # Find all text nodes in the current state of the soup.
            # This is done in each iteration because the soup is modified.
            text_nodes = soup.find_all(text=True)
            for node in text_nodes:
                # Skip nodes that are comments, doctypes, cdata, or inside script, style, or existing mark tags.
                if isinstance(node, (Comment, Doctype, CData)) or \
                   (node.parent and node.parent.name in ['script', 'style', 'mark']):
                    continue

                if text_val in node.string:
                    new_node_content = []
                    parts = node.string.split(text_val)
                    for i, part_text in enumerate(parts):
                        if part_text:
                            new_node_content.append(NavigableString(part_text))
                        if i < len(parts) - 1:  # Add mark tag if not the last part
                            mark_tag = soup.new_tag("mark")
                            mark_tag.string = text_val
                            
                            current_field_color = FIELD_COLOR_MAP.get(field_name, FIELD_COLOR_MAP["default_highlight"])
                            
                            # Apply all styles inline for <mark> tags to ensure precedence
                            mark_tag.attrs['style'] = (
                                f"background-color: {current_field_color} !important; "
                                f"color: black !important; "
                                f"font-weight: bold !important; "
                                f"padding: 0.1em 0.2em !important; "
                                f"border-radius: 0.2em !important;"
                            )
                            new_node_content.append(mark_tag)
                    
                    # Replace the original node with the new sequence of strings and tags
                    if new_node_content:
                        node.replace_with(*new_node_content)
        
        highlighted_html_for_iframe = str(soup).replace("'", "&apos;")

        # --- Prepare contact_sections for iframe display ---
        # Ensure contact_sections is a string, escape for srcdoc
        contact_sections_str = contact_sections if isinstance(contact_sections, str) else ""
        contact_sections_escaped_for_iframe = html.escape(contact_sections_str).replace("'", "&apos;")


        # --- Format the extracted office information as HTML ---
        offices_html = ""
        for i, office in enumerate(extracted_offices, 1):
            offices_html += f"<div class='office'><h3>Office #{i}</h3>"
            offices_html += "<table>"
            
            # Add each field
            for field in ["office_type", "building", "address", "suite", "city", "state", "zip", "phone", "fax", "hours"]:
                if field in office and office[field] is not None:
                    field_value = html.escape(str(office[field])) # Escape HTML characters in the value
                    # Wrap the value in a span with the field-specific class for coloring
                    offices_html += f"<tr><td><strong>{field.capitalize()}</strong></td><td><span class='highlighted-llm-output field-{field.lower()}'>{field_value}</span></td></tr>"
            
            offices_html += "</table></div>"
        
        # If no offices were found
        if not extracted_offices:
            offices_html = "<p>No district offices were found.</p>"
        
        # Determine validation mode
        validation_mode = "browser" if self.browser_validation and self.validation_server else "terminal"
        validation_port = self.validation_server.port if self.validation_server else 0
        
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
                .original-html-iframe {{ width: 100%; height: 600px; border: 1px solid #ddd; }}
                .llm-input-iframe {{ width: 100%; height: 300px; border: 1px solid #ccc; margin-bottom:20px;}}
                .note {{ background-color: #f8f9fa; padding: 10px; border-left: 4px solid #007bff; margin-bottom: 20px; }}
                .validation-buttons {{
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    display: flex;
                    gap: 10px;
                    background: white;
                    padding: 15px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.2);
                    z-index: 1000;
                }}
                .validation-button {{
                    padding: 10px 20px;
                    font-size: 16px;
                    font-weight: bold;
                    border: none;
                    border-radius: 5px;
                    cursor: pointer;
                    transition: all 0.2s;
                }}
                .accept-button {{
                    background-color: #4CAF50;
                    color: white;
                }}
                .accept-button:hover {{
                    background-color: #45a049;
                }}
                .reject-button {{
                    background-color: #f44336;
                    color: white;
                }}
                .reject-button:hover {{
                    background-color: #da190b;
                }}
                .highlighted-llm-output {{ 
                    /* This class is used for both <mark> in iframe and <span> in the table */
                    color: black; /* Text color for highlighted items */
                    font-weight: bold; 
                    padding: 0.1em 0.2em; 
                    border-radius: 0.2em; 
                }}
                /* Field-specific background colors for SPANs in the table. <mark> tags use inline styles. */
                span.highlighted-llm-output.field-address {{ background-color: {FIELD_COLOR_MAP['address']} !important; }}
                span.highlighted-llm-output.field-zip {{ background-color: {FIELD_COLOR_MAP['zip']} !important; }}
                span.highlighted-llm-output.field-phone {{ background-color: {FIELD_COLOR_MAP['phone']} !important; }}
                span.highlighted-llm-output.field-city {{ background-color: {FIELD_COLOR_MAP['city']} !important; }}
                span.highlighted-llm-output.field-state {{ background-color: {FIELD_COLOR_MAP['state']} !important; }}
                span.highlighted-llm-output.field-office_type {{ background-color: {FIELD_COLOR_MAP['office_type']} !important; }}
                span.highlighted-llm-output.field-building {{ background-color: {FIELD_COLOR_MAP['building']} !important; }}
                span.highlighted-llm-output.field-suite {{ background-color: {FIELD_COLOR_MAP['suite']} !important; }}
                span.highlighted-llm-output.field-fax {{ background-color: {FIELD_COLOR_MAP['fax']} !important; }}
                span.highlighted-llm-output.field-hours {{ background-color: {FIELD_COLOR_MAP['hours']} !important; }}
                /* Default highlight for SPANs without a specific field class */
                span.highlighted-llm-output:not([class*="field-"]) {{ 
                    background-color: {FIELD_COLOR_MAP['default_highlight']}; /* This fallback should not use !important for spans unless necessary */
                }}
            </style>
        </head>
        <body>
            <h1>District Office Validation - {bioguide_id}</h1>
            <p><strong>Source URL:</strong> <a href="{url}" target="_blank">{url}</a></p>
            
            <div class="note">
                <p><strong>Note:</strong> Review the LLM's input and output (left panel) and compare with the original HTML (right panel). 
                Highlighted text in the right panel corresponds to data extracted by the LLM.</p>
                {'<p><strong>Click the buttons below to accept or reject the extraction.</strong></p>' if validation_mode == 'browser' else '<p>Then return to the command line to confirm.</p>'}
            </div>
            
            <div class="container">
                <div class="left-panel">
                    <h2>LLM Input (Contact Sections)</h2>
                    <div class="llm-input-display">
                        <iframe class="llm-input-iframe" srcdoc='{contact_sections_escaped_for_iframe}' title="LLM Input HTML Snippets"></iframe>
                    </div>

                    <h2>Extracted Office Information (LLM Output)</h2>
                    {offices_html}
                </div>
                
                <div class="right-panel">
                    <h2>Original Page Content (with LLM extractions highlighted)</h2>
                    <iframe class="original-html-iframe" srcdoc='{highlighted_html_for_iframe}' title="Original HTML with Highlights"></iframe>
                </div>
            </div>
            
            {'<div class="validation-buttons"><button class="validation-button accept-button" onclick="submitValidation(\'accept\')">✓ Accept</button><button class="validation-button reject-button" onclick="submitValidation(\'reject\')">✗ Reject</button></div>' if validation_mode == 'browser' else ''}
            
            {f'''
            <script>
            function submitValidation(decision) {{
                const url = `http://localhost:{validation_port}/validate?decision=${{decision}}&bioguide_id={bioguide_id}`;
                fetch(url)
                    .then(response => {{
                        if (response.ok) {{
                            document.body.innerHTML = response.text().then(html => document.body.innerHTML = html);
                        }} else {{
                            alert('Error submitting validation. Please check the console.');
                        }}
                    }})
                    .catch(error => {{
                        console.error('Error:', error);
                        alert('Failed to submit validation. Please use the terminal instead.');
                    }});
            }}
            </script>
            ''' if validation_mode == 'browser' else ''}
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
            # Try zen-browser first
            try:
                log.info(f"Attempting to open validation interface with zen-browser at {url}")
                subprocess.run(['zen-browser', '--new-window', url], check=True)
                log.info(f"Successfully opened with zen-browser: {url}")
            except (subprocess.CalledProcessError, FileNotFoundError):
                log.warning(f"zen-browser command failed or not found. Falling back to default browser.")
                try:
                    # Fallback to webbrowser.open
                    log.info(f"Opening validation interface with default browser at {url}")
                    webbrowser.open(url, new=1) # new=1 requests a new window
                except Exception as e_web:
                    log.error(f"Failed to open validation interface with fallback browser: {e_web}")
        except Exception as e_main:
            # Catch any other unexpected error during the initial setup (e.g., os.path.abspath)
            log.error(f"Failed to open validation interface: {e_main}")
    
    def open_validation_interface_nonblocking(self, validation_html_path: str) -> None:
        """Open the validation interface in a web browser without blocking.
        
        Args:
            validation_html_path: Path to the validation HTML file
        """
        try:
            url = f"file://{os.path.abspath(validation_html_path)}"
            log.info(f"Opening validation interface at {url} (non-blocking)")
            
            # Define browser commands, prioritizing zen-browser
            browser_commands = [
                ['zen-browser', '--new-window', url], # Prioritize zen-browser with new window
                ['xdg-open', url],    # Linux default
                ['open', url],        # macOS
            ]
            
            for cmd in browser_commands:
                try:
                    # Use Popen with detached process to avoid blocking
                    subprocess.Popen(
                        cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    log.info(f"Successfully launched browser with command: {cmd}")
                    return
                except (subprocess.SubprocessError, FileNotFoundError):
                    log.debug(f"Command {cmd} failed or not found, trying next.")
                    continue # Try the next command
            
            # Fallback to webbrowser module if all specific subprocess approaches fail
            log.warning("All specific browser commands failed, falling back to webbrowser.open")
            webbrowser.open(url, new=1) # new=1 requests a new window
            
        except Exception as e:
            log.error(f"Failed to open validation interface: {e}")
    
    def validate_office_data(
        self,
        bioguide_id: str,
        offices: List[Dict[str, Any]],
        html_content: str,
        url: str,
        contact_sections: str,
        extraction_id: Optional[int] = None
    ) -> Tuple[bool, Optional[List[Dict[str, Any]]]]:
        """Validate the extracted office data through human review.
        
        Args:
            bioguide_id: The bioguide ID being processed
            offices: The extracted office information
            html_content: The HTML content from the representative's page
            url: The URL that was scraped
            contact_sections: The HTML sections fed to the LLM
            
        Returns:
            Tuple of (is_validated, validated_offices)
        """
        # Start validation server if using browser validation
        if self.browser_validation:
            from district_offices.validation.server import ValidationServer
            self.validation_server = ValidationServer()
            self.validation_server.start()
            
        # Generate the validation HTML
        validation_html_path = self.generate_validation_html(
            bioguide_id, html_content, offices, url, contact_sections
        )
        
        # Open the validation interface in browser
        self.open_validation_interface(validation_html_path)
        
        is_valid = None
        
        if self.browser_validation and self.validation_server:
            # Browser-based validation
            print("\nA browser window should have opened with the validation interface.")
            print(f"Please review the district office information for {bioguide_id}.")
            print("Click the Accept or Reject button in the browser to continue...")
            
            # Wait for browser response
            result = self.validation_server.wait_for_validation(timeout=300)
            
            if result:
                is_valid = result['decision'] == 'accept'
                print(f"\nValidation {result['decision']}ed via browser")
            else:
                print("\nTimeout waiting for browser response. Falling back to terminal input.")
                # Fall back to terminal input
                while is_valid is None:
                    response = input("Is the extracted information correct? (Y/n): ").strip().lower()
                    if response == "" or response == "y":
                        is_valid = True
                    elif response == "n":
                        is_valid = False
                    else:
                        print("Please enter 'Y' or 'n'")
            
            # Stop the validation server
            self.validation_server.stop()
            self.validation_server = None
        else:
            # Terminal-based validation (original behavior)
            print("\nA browser window should have opened with the validation interface.")
            print(f"Please review the district office information for {bioguide_id}.")
            
            # Get user input
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
            self._save_validated_data(bioguide_id, offices, html_content, url, extraction_id)
            
            return True, offices
        else:
            log.info(f"User rejected office data for {bioguide_id}")
            
            # Save the rejected data
            self._save_rejected_data(bioguide_id, offices, html_content, url, extraction_id)
            
            return False, None
    
    def _save_validated_data(
        self, 
        bioguide_id: str, 
        offices: List[Dict[str, Any]], 
        html_content: str,
        url: str,
        extraction_id: Optional[int] = None
    ) -> None:
        """Save validated data to SQLite.
        
        Args:
            bioguide_id: The bioguide ID being processed
            offices: The extracted office information
            html_content: The HTML content from the representative's page
            url: The URL that was scraped
            extraction_id: Optional extraction ID to update
        """
        timestamp = int(time.time())
        
        # If we have an extraction_id, update its status
        if extraction_id:
            self.db.update_extraction_status(extraction_id, 'validated')
            
            # Store validation artifacts
            validation_data = {
                "bioguide_id": bioguide_id,
                "url": url,
                "offices": offices,
                "validation_timestamp": timestamp,
                "validation_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.db.store_artifact(
                extraction_id=extraction_id,
                artifact_type='validation_result',
                filename=f"{bioguide_id}_{timestamp}_validation.json",
                content=json.dumps(validation_data, indent=2).encode('utf-8'),
                content_type='application/json'
            )
        
        # Create validated office records
        for office in offices:
            office_id = f"{bioguide_id}-{office.get('city', 'unknown')}-{timestamp}"
            # Merge all data into a single dictionary
            validated_office_data = {
                'office_id': office_id,
                'bioguide_id': bioguide_id,
                **office  # Include all office fields
            }
            self.db.create_validated_office(validated_office_data)
        
        log.info(f"Saved validated data for {bioguide_id} to SQLite")
    
    def _save_rejected_data(
        self, 
        bioguide_id: str, 
        offices: List[Dict[str, Any]], 
        html_content: str,
        url: str,
        extraction_id: Optional[int] = None
    ) -> None:
        """Save rejected data to SQLite.
        
        Args:
            bioguide_id: The bioguide ID being processed
            offices: The extracted office information
            html_content: The HTML content from the representative's page
            url: The URL that was scraped
            extraction_id: Optional extraction ID to update
        """
        timestamp = int(time.time())
        
        # If we have an extraction_id, update its status
        if extraction_id:
            self.db.update_extraction_status(extraction_id, 'rejected')
            
            # Store rejection artifacts
            rejection_data = {
                "bioguide_id": bioguide_id,
                "url": url,
                "offices": offices,
                "rejection_timestamp": timestamp,
                "rejection_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self.db.store_artifact(
                extraction_id=extraction_id,
                artifact_type='rejection_result',
                filename=f"{bioguide_id}_{timestamp}_rejection.json",
                content=json.dumps(rejection_data, indent=2).encode('utf-8'),
                content_type='application/json'
            )
        
        log.info(f"Saved rejected data for {bioguide_id} to SQLite")
