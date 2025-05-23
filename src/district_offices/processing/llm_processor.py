#!/usr/bin/env python3

import logging
import os
import sys
import json
import time
from typing import Dict, List, Optional, Any

# Import LiteLLM for multi-provider LLM support
import litellm

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

class LLMProcessor:
    """Class for processing HTML content using LiteLLM for multi-provider LLM support."""
    
    def __init__(self, model_name: str = "claude-3-haiku-20240307", api_key: Optional[str] = None):
        """Initialize the LLM processor.
        
        Args:
            model_name: LiteLLM compatible model string (e.g., "claude-3-haiku-20240307", "gpt-4-turbo")
            api_key: Optional API key. LiteLLM typically uses environment variables.
        """
        # Store the LiteLLM model string
        self.model = model_name
        
        # Create directory for storing LLM responses
        self.results_dir = os.path.join(os.path.dirname(__file__), "cache", "llm_results")
        os.makedirs(self.results_dir, exist_ok=True)
        
        log.info(f"Initialized LLMProcessor with model: {self.model}")
        
        # Check for relevant API keys (LiteLLM handles these via environment variables)
        relevant_api_keys = [
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", 
            "COHERE_API_KEY", "REPLICATE_API_TOKEN"
        ]
        api_key_present = any(os.environ.get(key) for key in relevant_api_keys)
        
        if not api_key_present:
            log.warning("No relevant LLM API key found in environment variables. Will simulate responses for development.")
    
    def _clean_html_content(self, html_content: str) -> str:
        """Clean HTML content by removing script, style, and other non-content elements.
        
        Args:
            html_content: Raw HTML content to clean
            
        Returns:
            Cleaned HTML content as string
        """
        from bs4 import BeautifulSoup
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Remove script, style, meta, and SVG tags to clean up the HTML
            for tag in soup(['script', 'style', 'meta', 'link', 'head', 'svg', 'path', 'clippath', 'g']):
                tag.decompose()
            
            # Get the cleaned HTML content
            cleaned_html = str(soup)
            log.info("Successfully cleaned HTML content by removing script/style tags")
            return cleaned_html
            
        except Exception as e:
            log.warning(f"Error cleaning HTML: {e}, using original content")
            return html_content
        
    def generate_system_prompt(self) -> str:
        """Generate the system prompt for the LLM.
        
        Returns:
            System prompt string
        """
        return """
        You are a specialized assistant tasked with extracting congressional district office information from HTML webpage content.
        
        You will be provided with structured HTML content from a representative's contact page. Your job is to carefully parse this HTML and find all district offices and extract the exact contact information.
        
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
        - You will receive HTML content, not plain text
        - Look for HTML elements that contain office information: <div>, <section>, <address>, <p>, <span>, etc.
        - Pay attention to HTML structure - office information is often grouped in containers
        - Look for headings like <h1>, <h2>, <h3> that indicate "Office Locations", "Contact", "District Offices"
        - Office information may be in lists (<ul>, <ol>, <li>) or tables (<table>, <tr>, <td>)
        - Extract ALL offices found, not just the first one
        - Maintain exact formatting of addresses, phone numbers, etc. as shown in the HTML text content
        - Omit any field if information is missing (don't guess or make up information)
        - Return a JSON array with each object representing one office
        - Use these exact field names: "office_type", "building", "address", "suite", "city", "state", "zip", "phone", "fax", "hours"
        
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
        """Extract district office information from HTML content using the LLM via LiteLLM.
        
        Args:
            html_content: Structured HTML content from the representative's contact page.
            bioguide_id: Bioguide ID for reference.
            
        Returns:
            List of dictionaries containing extracted district office information.
        """
        # Generate unique ID for this extraction
        extraction_id = f"{bioguide_id}_{int(time.time())}"
        
        # Check for API keys based on environment variables
        relevant_api_keys = [
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", 
            "COHERE_API_KEY", "REPLICATE_API_TOKEN"
        ]
        api_key_present = any(os.environ.get(key) for key in relevant_api_keys)
        
        if not api_key_present:
            # Simulate a response for development without API key
            log.warning("Using simulated LLM response (no relevant API key found)")
            simulated_response = self._simulate_response(html_content, bioguide_id)
            
            # Save simulated response for reference
            result_path = os.path.join(self.results_dir, f"{extraction_id}_simulated.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(simulated_response, f, indent=2)
            
            return simulated_response
        
        system_prompt = self.generate_system_prompt()
        
        # Clean the HTML content
        cleaned_html = self._clean_html_content(html_content)
        
        # Ensure cleaned HTML is not excessively long. Truncation might still be needed,
        # but be mindful that truncating HTML can break its structure.
        max_html_length = 150000  # Adjust as needed, token limits are the real concern
        if len(cleaned_html) > max_html_length:
            log.warning(f"HTML content too long ({len(cleaned_html)} chars), truncating to {max_html_length} chars. This might break HTML structure.")
            user_content = cleaned_html[:max_html_length]
        else:
            user_content = cleaned_html
        
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}  # Send structured HTML
        ]
        
        try:
            log.info(f"Calling LLM ({self.model}) via LiteLLM to extract district offices for {bioguide_id}")
            
            # Make the API call using LiteLLM
            response = litellm.completion(
                model=self.model,
                messages=llm_messages,
                max_tokens=4000  # Adjust as needed
            )
            
            # Cost Tracking
            try:
                cost = litellm.completion_cost(completion_response=response)
                log.info(f"LLM call cost for {extraction_id}: ${cost:.6f}")
                # Store this cost for tracking purposes
            except Exception as cost_e:
                log.warning(f"Could not calculate cost for {extraction_id}: {cost_e}")
            
            # Extract the JSON from the LLM's response
            response_text = response.choices[0].message.content
            
            # Parse the JSON response
            try:
                
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
                f.write(f"Model: {self.model}\n\n{response_text}")
            
            # Save extracted offices for reference
            result_path = os.path.join(self.results_dir, f"{extraction_id}.json")
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result_json, f, indent=2)
            
            log.info(f"Successfully extracted {len(result_json)} district offices for {bioguide_id} using {self.model}")
            return result_json
            
        except litellm.exceptions.APIConnectionError as e:
            log.error(f"LiteLLM API Connection Error: {e}")
            return []
        except litellm.exceptions.RateLimitError as e:
            log.error(f"LiteLLM Rate Limit Error: {e}")
            # Implement retry logic or backoff if needed
            return []
        except litellm.exceptions.APIError as e:  # Catch other LiteLLM API errors
            log.error(f"LiteLLM API Error: {e}")
            return []
        except Exception as e:  # Catch-all for other unexpected errors
            log.error(f"Failed to extract district offices with LLM ({self.model}): {e}")
            # Log the full traceback for unexpected errors
            import traceback
            log.error(traceback.format_exc())
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