#!/usr/bin/env python3

import logging
import os
import sys
import json
import time
from typing import Dict, List, Optional, Any

# Import the Anthropic SDK
import anthropic

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

class LLMProcessor:
    """Class for processing HTML content using Anthropic's Claude LLM."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the LLM processor.
        
        Args:
            api_key: Anthropic API key (optional, can use env var)
        """
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            log.warning("No Anthropic API key provided. Will simulate responses for development.")
        
        # Initialize Anthropic client if API key is available
        if self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
            log.info("Initialized Anthropic client with provided API key")
        
        # Create directory for storing LLM responses
        self.results_dir = os.path.join(os.path.dirname(__file__), "cache", "llm_results")
        os.makedirs(self.results_dir, exist_ok=True)
        
        # Set the model to use
        self.model = "claude-3-7-sonnet-20250219"
        
    def generate_system_prompt(self) -> str:
        """Generate the system prompt for the LLM.
        
        Returns:
            System prompt string
        """
        return """
        You are a specialized assistant tasked with extracting congressional district office information from websites.
        
        Your job is to carefully find all district offices (NOT Washington DC offices) and extract the exact contact information.
        
        For EACH district office, extract:
        1. Office name (often a city name like "San Francisco Office" or "District Office")
        2. Building name (if specified)
        3. Street address (e.g., "123 Main Street")
        4. Suite/Room number (e.g., "Suite 100" or "Room 200")
        5. City
        6. State (two-letter code)
        7. ZIP code
        8. Phone number (exactly as written)
        9. Fax number (if available)
        10. Hours (if available)
        
        IMPORTANT INSTRUCTIONS:
        - DO NOT include the Washington DC office - focus only on district/local offices
        - Extract ALL offices found, not just the first one
        - Maintain exact formatting of addresses, phone numbers, etc. as shown on the page
        - Omit any field if information is missing (don't guess)
        - Focus on sections with "Office Locations", "Contact", or similar headings
        - Return a JSON array with each object representing one office
        - Use these exact field names: "office_type", "building", "address", "suite", "city", "state", "zip", "phone", "fax", "hours"
        - Look for district office sections near the bottom of the page or in sidebars
        
        Example response:
        ```json
        [
          {
            "office_type": "San Francisco Office",
            "address": "100 Main Street", 
            "suite": "Suite 200",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94102",
            "phone": "(415) 555-1234"
          },
          {
            "office_type": "Los Angeles Office",
            "building": "Federal Building",
            "address": "300 Center Ave",
            "suite": "Suite 505",
            "city": "Los Angeles",
            "state": "CA",
            "zip": "90012",
            "phone": "(213) 555-6789",
            "fax": "(213) 555-9876",
            "hours": "Monday-Friday 9am-5pm"
          }
        ]
        ```
        
        Focus only on returning the JSON array with the extracted information. Return an empty array `[]` if no district offices are found.
        """

    def extract_district_offices(self, html_content: str, bioguide_id: str) -> List[Dict[str, Any]]:
        """Extract district office information from HTML content using the LLM.
        
        Args:
            html_content: HTML content from the representative's contact page
            bioguide_id: Bioguide ID for reference
            
        Returns:
            List of dictionaries containing extracted district office information
        """
        # Generate unique ID for this extraction
        extraction_id = f"{bioguide_id}_{int(time.time())}"
        
        if not self.api_key:
            # Simulate a response for development without API key
            log.warning("Using simulated LLM response (no API key provided)")
            simulated_response = self._simulate_response(html_content, bioguide_id)
            
            # Save simulated response for reference
            result_path = os.path.join(self.results_dir, f"{extraction_id}_simulated.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(simulated_response, f, indent=2)
            
            return simulated_response
        
        # Call the Anthropic API
        try:
            log.info(f"Calling Anthropic API to extract district offices for {bioguide_id}")
            
            system_prompt = self.generate_system_prompt()
            
            # Process the HTML to focus on relevant content
            from bs4 import BeautifulSoup
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Remove script, style, meta, and SVG tags to clean up the HTML
                for tag in soup(['script', 'style', 'meta', 'link', 'head', 'svg', 'path', 'clippath', 'g']):
                    tag.decompose()
                
                # Find specific sections likely to contain office information
                contact_sections = []
                
                # Look for sections with office locations, contact info
                for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    text = heading.get_text().lower()
                    if any(term in text for term in ['office', 'location', 'contact']):
                        section = heading
                        # Get the parent if it's a container
                        if heading.parent and heading.parent.name in ['div', 'section']:
                            section = heading.parent
                        contact_sections.append(str(section))
                
                # Also look for divs with specific classes or IDs
                for div in soup.find_all('div'):
                    div_id = div.get('id', '').lower()
                    div_class = ' '.join(div.get('class', [])).lower()
                    
                    if any(term in div_id for term in ['office', 'location', 'contact']) or \
                       any(term in div_class for term in ['office', 'location', 'contact']):
                        contact_sections.append(str(div))
                
                # If we found specific sections, use those instead of the full HTML
                if contact_sections:
                    html_content = "\n".join(contact_sections)
                    log.info(f"Extracted {len(contact_sections)} relevant contact sections")
                
                # Further clean by converting to plain text with structure
                soup = BeautifulSoup(html_content, 'html.parser')
                text_content = soup.get_text(separator='\n', strip=True)
                
                # Ensure we're within context limits
                max_text_length = 60000
                if len(text_content) > max_text_length:
                    log.warning(f"Content too long ({len(text_content)} chars), truncating to {max_text_length} chars")
                    text_content = text_content[:max_text_length]
                
                # Construct a simple prompt with the extracted content
                user_content = f"""
Please extract the district office information from the following website content:

{text_content}

Remember to find all district offices (not Washington DC offices) and provide the requested details in JSON format.
"""
                
            except Exception as e:
                log.error(f"Error processing HTML: {e}")
                # Fall back to truncated raw HTML
                max_html_length = 60000
                if len(html_content) > max_html_length:
                    log.warning(f"HTML content too long ({len(html_content)} chars), truncating to {max_html_length} chars")
                    html_content = html_content[:max_html_length]
                user_content = html_content
            
            # Make the API call to Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_content}
                ]
            )
            
            # Extract the JSON from Claude's response
            try:
                response_text = response.content[0].text
                
                # More robust JSON extraction
                # Try different patterns to extract JSON
                json_text = None
                
                # Pattern 1: ```json ... ```
                if "```json" in response_text:
                    try:
                        json_text = response_text.split("```json")[1].split("```")[0].strip()
                        result_json = json.loads(json_text)
                    except (json.JSONDecodeError, IndexError):
                        json_text = None
                
                # Pattern 2: ``` ... ```
                if json_text is None and "```" in response_text:
                    try:
                        json_text = response_text.split("```")[1].split("```")[0].strip()
                        result_json = json.loads(json_text)
                    except (json.JSONDecodeError, IndexError):
                        json_text = None
                
                # Pattern 3: [ ... ] (direct JSON array)
                if json_text is None:
                    try:
                        # Look for array pattern
                        import re
                        array_pattern = r'\[\s*\{.*\}\s*\]'
                        array_match = re.search(array_pattern, response_text, re.DOTALL)
                        if array_match:
                            json_text = array_match.group(0)
                            result_json = json.loads(json_text)
                        else:
                            # Just try the whole response
                            json_text = response_text
                            result_json = json.loads(json_text)
                    except json.JSONDecodeError:
                        # Fall back to empty array if we can't parse JSON
                        log.error(f"Failed to parse JSON response, returning empty array")
                        result_json = []
                
                # Ensure the result is a list
                if not isinstance(result_json, list):
                    log.warning(f"LLM response is not a list, converting: {type(result_json)}")
                    if isinstance(result_json, dict):
                        if "offices" in result_json:
                            result_json = result_json["offices"]
                        else:
                            # Just use the dict as a single item
                            result_json = [result_json]
                    else:
                        result_json = []
                
            except (json.JSONDecodeError, IndexError) as e:
                log.error(f"Failed to parse LLM response as JSON: {e}")
                log.error(f"Raw response: {response_text}")
                return []
            
            # Save the full response for reference
            response_path = os.path.join(self.results_dir, f"{extraction_id}_response.txt")
            with open(response_path, 'w', encoding='utf-8') as f:
                f.write(response_text)
            
            # Save extracted offices for reference
            result_path = os.path.join(self.results_dir, f"{extraction_id}.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result_json, f, indent=2)
            
            log.info(f"Successfully extracted {len(result_json)} district offices for {bioguide_id}")
            return result_json
            
        except Exception as e:
            log.error(f"Failed to extract district offices with LLM: {e}")
            return []
    
    def _simulate_response(self, html_content: str, bioguide_id: str) -> List[Dict[str, Any]]:
        """Simulate an LLM response for development purposes.
        
        Args:
            html_content: HTML content from the representative's contact page
            bioguide_id: Bioguide ID for reference
            
        Returns:
            Simulated LLM response as a list of dictionaries
        """
        # Basic simulation of district office extraction
        # In a real implementation, this would be replaced by the actual LLM call
        
        # Check if HTML contains certain keywords to simulate finding offices
        if "office location" in html_content.lower() or "district office" in html_content.lower():
            # Simulate finding 1-3 offices
            import random
            num_offices = random.randint(1, 3)
            
            offices = []
            for i in range(num_offices):
                office = {
                    "office_type": "District Office",
                    "address": f"{100 + i*100} Main Street",
                    "city": f"City{i+1}",
                    "state": "CA",
                    "zip": f"9{i+1}000",
                    "phone": f"(555) 555-{1000+i}"
                }
                
                # Randomly add some optional fields
                if random.choice([True, False]):
                    office["suite"] = f"Suite {200 + i*100}"
                if random.choice([True, False]):
                    office["building"] = "Federal Building"
                if random.choice([True, False]):
                    office["fax"] = f"(555) 555-{2000+i}"
                if random.choice([True, False]):
                    office["hours"] = "Monday-Friday 9am-5pm"
                    
                offices.append(office)
                
            return offices
        else:
            # Simulate not finding any offices
            return []

    def format_for_display(self, offices: List[Dict[str, Any]], bioguide_id: str) -> str:
        """Format the extracted office information for display to humans.
        
        Args:
            offices: List of office dictionaries
            bioguide_id: Bioguide ID for reference
            
        Returns:
            Formatted string for display
        """
        if not offices:
            return f"No district offices found for representative {bioguide_id}."
        
        formatted = f"Found {len(offices)} district office(s) for representative {bioguide_id}:\n\n"
        
        for i, office in enumerate(offices, 1):
            formatted += f"Office #{i}:\n"
            if "office_type" in office:
                formatted += f"Type: {office['office_type']}\n"
            if "building" in office:
                formatted += f"Building: {office['building']}\n"
            
            # Address components
            address_parts = []
            if "address" in office:
                address_parts.append(office["address"])
            if "suite" in office:
                address_parts.append(office["suite"])
            if address_parts:
                formatted += f"Address: {', '.join(address_parts)}\n"
                
            # City, State ZIP
            location_parts = []
            if "city" in office:
                location_parts.append(office["city"])
            if "state" in office and "zip" in office:
                location_parts.append(f"{office['state']} {office['zip']}")
            elif "state" in office:
                location_parts.append(office["state"])
            elif "zip" in office:
                location_parts.append(office["zip"])
            if location_parts:
                formatted += f"Location: {', '.join(location_parts)}\n"
            
            # Contact info
            if "phone" in office:
                formatted += f"Phone: {office['phone']}\n"
            if "fax" in office:
                formatted += f"Fax: {office['fax']}\n"
            if "hours" in office:
                formatted += f"Hours: {office['hours']}\n"
                
            formatted += "\n"
            
        return formatted