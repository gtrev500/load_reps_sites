#!/usr/bin/env python3
"""Async validation interface for district office data."""

import asyncio
import logging
import os
import json
import tempfile
import webbrowser
from typing import Dict, List, Optional, Any, Tuple
import aiofiles
from bs4 import BeautifulSoup

from district_offices.validation.server import ValidationServer

log = logging.getLogger(__name__)

# Field styling configuration (reuse from sync version)
from district_offices.validation.interface import (
    FIELD_COLOR_MAP,
    FIELD_HIGHLIGHT_PRIORITY,
)


class AsyncValidationInterface:
    """Async interface for validating extracted district office data."""
    
    def __init__(self):
        """Initialize the async validation interface."""
        self.validation_server = None
    
    async def validate_offices(
        self,
        offices: List[Dict[str, Any]],
        contact_sections: List[str],
        bioguide_id: str,
        screenshot_path: Optional[str] = None,
        use_browser: bool = False,
        timeout: int = 300
    ) -> Optional[List[Dict[str, Any]]]:
        """Validate extracted office data with human review.
        
        Args:
            offices: List of extracted office dictionaries
            contact_sections: HTML sections used for extraction
            bioguide_id: Bioguide ID of the representative
            screenshot_path: Optional path to screenshot
            use_browser: Whether to use browser-based validation
            timeout: Timeout in seconds for browser validation
            
        Returns:
            Validated offices or None if rejected
        """
        if not offices:
            log.warning("No offices to validate")
            return None
        
        # Generate validation HTML
        html_content = await self._generate_validation_html(
            offices, contact_sections, bioguide_id, screenshot_path
        )
        
        # Save to temporary file
        temp_file = await self._save_temp_html(html_content)
        
        try:
            if use_browser:
                # Browser-based validation
                result = await self._browser_validation(temp_file, timeout)
            else:
                # Terminal-based validation
                result = await self._terminal_validation(temp_file, offices)
            
            return result
            
        finally:
            # Cleanup
            if temp_file and os.path.exists(temp_file):
                os.unlink(temp_file)
    
    async def _generate_validation_html(
        self,
        offices: List[Dict[str, Any]],
        contact_sections: List[str],
        bioguide_id: str,
        screenshot_path: Optional[str] = None
    ) -> str:
        """Generate HTML for validation interface."""
        # Highlight fields in contact sections
        highlighted_sections = []
        for section in contact_sections:
            highlighted = self._highlight_fields_in_section(section, offices)
            highlighted_sections.append(highlighted)
        
        # Format offices as JSON
        offices_json = json.dumps(offices, indent=2)
        
        # Build HTML
        html_parts = [
            '<!DOCTYPE html>',
            '<html><head>',
            '<meta charset="UTF-8">',
            '<title>Validate District Offices - ' + bioguide_id + '</title>',
            '<style>',
            self._get_css_styles(),
            '</style>',
            '</head><body>',
            '<div class="container">',
            f'<h1>Validate District Offices for {bioguide_id}</h1>',
        ]
        
        # Add extracted data
        html_parts.extend([
            '<div class="section">',
            '<h2>Extracted Office Data</h2>',
            '<pre class="json-data">' + offices_json + '</pre>',
            '</div>',
        ])
        
        # Add source sections
        html_parts.extend([
            '<div class="section">',
            '<h2>Source HTML Sections</h2>',
        ])
        
        for i, section in enumerate(highlighted_sections):
            html_parts.extend([
                f'<div class="source-section">',
                f'<h3>Section {i + 1}</h3>',
                f'<div class="html-content">{section}</div>',
                '</div>',
            ])
        
        html_parts.append('</div>')
        
        # Add screenshot if available
        if screenshot_path and os.path.exists(screenshot_path):
            html_parts.extend([
                '<div class="section">',
                '<h2>Page Screenshot</h2>',
                f'<img src="file://{screenshot_path}" alt="Screenshot" style="max-width: 100%;">',
                '</div>',
            ])
        
        # Add validation buttons for browser mode
        html_parts.extend([
            '<div class="validation-buttons">',
            '<button onclick="validateOffices(true)" class="accept-btn">Accept</button>',
            '<button onclick="validateOffices(false)" class="reject-btn">Reject</button>',
            '</div>',
            '<script>',
            self._get_javascript(),
            '</script>',
            '</div></body></html>',
        ])
        
        return '\n'.join(html_parts)
    
    def _highlight_fields_in_section(
        self, 
        section_html: str, 
        offices: List[Dict[str, Any]]
    ) -> str:
        """Highlight extracted fields in HTML section."""
        soup = BeautifulSoup(section_html, 'html.parser')
        
        # Collect all field values to highlight
        highlights = []
        for office in offices:
            for field, value in office.items():
                if value and field in FIELD_COLOR_MAP:
                    highlights.append({
                        'field': field,
                        'value': str(value),
                        'color': FIELD_COLOR_MAP[field],
                        'priority': FIELD_HIGHLIGHT_PRIORITY.get(field, 99)
                    })
        
        # Sort by length (longest first) and priority
        highlights.sort(key=lambda x: (-len(x['value']), x['priority']))
        
        # Apply highlights
        for highlight in highlights:
            self._highlight_text_in_soup(
                soup, 
                highlight['value'], 
                highlight['color'],
                highlight['field']
            )
        
        return str(soup)
    
    def _highlight_text_in_soup(
        self, 
        soup: BeautifulSoup, 
        text: str, 
        color: str,
        field_type: str
    ):
        """Highlight specific text in BeautifulSoup object."""
        from bs4 import NavigableString, Tag
        
        def replace_in_element(element):
            if isinstance(element, NavigableString):
                parent = element.parent
                if parent and parent.name not in ['script', 'style', 'mark']:
                    new_content = str(element)
                    if text.lower() in new_content.lower():
                        # Create highlighted version
                        import re
                        pattern = re.compile(re.escape(text), re.IGNORECASE)
                        parts = pattern.split(new_content)
                        
                        if len(parts) > 1:
                            new_elements = []
                            matches = pattern.findall(new_content)
                            
                            for i, part in enumerate(parts[:-1]):
                                if part:
                                    new_elements.append(NavigableString(part))
                                
                                # Create highlight tag
                                mark = soup.new_tag('mark')
                                mark.string = matches[i]
                                mark['style'] = f'background-color: {color};'
                                mark['data-field'] = field_type
                                mark['title'] = f'{field_type}: {matches[i]}'
                                new_elements.append(mark)
                            
                            if parts[-1]:
                                new_elements.append(NavigableString(parts[-1]))
                            
                            # Replace the original element
                            for i, elem in enumerate(new_elements):
                                if i == 0:
                                    element.replace_with(elem)
                                else:
                                    elem.previous_sibling.insert_after(elem)
        
        # Process all text nodes
        for element in list(soup.descendants):
            if isinstance(element, NavigableString):
                replace_in_element(element)
    
    def _get_css_styles(self) -> str:
        """Get CSS styles for validation HTML."""
        return """
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background-color: #f4f4f4;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }
        h1, h2, h3 {
            color: #333;
        }
        .section {
            margin-bottom: 30px;
            padding: 20px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .json-data {
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
        }
        .source-section {
            margin-bottom: 20px;
            padding: 15px;
            background-color: #fafafa;
            border: 1px solid #e0e0e0;
            border-radius: 5px;
        }
        .html-content {
            background-color: white;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 3px;
            overflow-x: auto;
        }
        mark {
            padding: 2px 4px;
            border-radius: 3px;
            font-weight: bold;
        }
        .validation-buttons {
            position: fixed;
            bottom: 20px;
            right: 20px;
            display: flex;
            gap: 10px;
        }
        .accept-btn, .reject-btn {
            padding: 10px 20px;
            font-size: 16px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            transition: background-color 0.3s;
        }
        .accept-btn {
            background-color: #4CAF50;
            color: white;
        }
        .accept-btn:hover {
            background-color: #45a049;
        }
        .reject-btn {
            background-color: #f44336;
            color: white;
        }
        .reject-btn:hover {
            background-color: #da190b;
        }
        """
    
    def _get_javascript(self) -> str:
        """Get JavaScript for browser validation."""
        return """
        function validateOffices(accepted) {
            // Send result to server
            fetch(`http://localhost:${window.validationPort || 8899}/validate`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({accepted: accepted})
            }).then(() => {
                window.close();
            }).catch(err => {
                console.error('Validation error:', err);
                alert('Error submitting validation. Please check console.');
            });
        }
        
        // Add keyboard shortcuts
        document.addEventListener('keydown', function(e) {
            if (e.key === 'a' || e.key === 'A') {
                validateOffices(true);
            } else if (e.key === 'r' || e.key === 'R') {
                validateOffices(false);
            }
        });
        """
    
    async def _save_temp_html(self, html_content: str) -> str:
        """Save HTML content to temporary file."""
        fd, temp_path = tempfile.mkstemp(suffix='.html', prefix='validation_')
        os.close(fd)
        
        async with aiofiles.open(temp_path, 'w', encoding='utf-8') as f:
            await f.write(html_content)
        
        return temp_path
    
    async def _browser_validation(
        self, 
        html_path: str, 
        timeout: int
    ) -> Optional[List[Dict[str, Any]]]:
        """Perform browser-based validation."""
        # Start validation server
        self.validation_server = ValidationServer()
        self.validation_server.start()
        port = self.validation_server.server.server_port
        
        # Open in browser with port info
        url = f"file://{html_path}?port={port}"
        webbrowser.open(url)
        
        log.info("Browser validation window opened. Press 'A' to accept or 'R' to reject.")
        
        # Wait for response
        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    self.validation_server.wait_for_result,
                    timeout
                ),
                timeout=timeout
            )
            
            if result and result.get('accepted'):
                log.info("Validation accepted")
                return True  # Return original offices
            else:
                log.info("Validation rejected")
                return None
                
        except asyncio.TimeoutError:
            log.warning("Browser validation timed out")
            return None
        finally:
            self.validation_server.stop()
    
    async def _terminal_validation(
        self, 
        html_path: str,
        offices: List[Dict[str, Any]]
    ) -> Optional[List[Dict[str, Any]]]:
        """Perform terminal-based validation."""
        # Open HTML in browser
        webbrowser.open(f"file://{html_path}")
        
        print("\n" + "="*60)
        print("VALIDATION REQUIRED")
        print("="*60)
        print(f"Extracted {len(offices)} office(s)")
        print("\nPlease review the opened browser window.")
        print("\nOptions:")
        print("  [A]ccept - Accept the extracted data")
        print("  [R]eject - Reject and skip this bioguide")
        print("  [Q]uit   - Exit the program")
        print("="*60)
        
        while True:
            choice = input("\nYour choice [A/R/Q]: ").strip().upper()
            
            if choice == 'A':
                log.info("User accepted the extracted data")
                return offices
            elif choice == 'R':
                log.info("User rejected the extracted data")
                return None
            elif choice == 'Q':
                log.info("User quit validation")
                raise KeyboardInterrupt("User quit validation")
            else:
                print("Invalid choice. Please enter A, R, or Q.")


# Convenience function for async validation
async def validate_offices_async(
    offices: List[Dict[str, Any]],
    contact_sections: List[str],
    bioguide_id: str,
    screenshot_path: Optional[str] = None,
    use_browser: bool = False,
    timeout: int = 300
) -> Optional[List[Dict[str, Any]]]:
    """Async convenience function for office validation.
    
    Args:
        offices: List of extracted office dictionaries
        contact_sections: HTML sections used for extraction
        bioguide_id: Bioguide ID of the representative
        screenshot_path: Optional path to screenshot
        use_browser: Whether to use browser-based validation
        timeout: Timeout in seconds for browser validation
        
    Returns:
        Validated offices or None if rejected
    """
    validator = AsyncValidationInterface()
    return await validator.validate_offices(
        offices, contact_sections, bioguide_id, 
        screenshot_path, use_browser, timeout
    )