#!/usr/bin/env python3

import logging
import os
import sys
import json
import time
from typing import Dict, List, Optional, Any

# Import LiteLLM for multi-provider LLM support
import litellm

# Import centralized configuration
from district_offices.config import Config
from district_offices.utils.html import clean_html

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

class LLMProcessor:
    """Class for processing HTML content using LiteLLM for multi-provider LLM support."""
    
    def __init__(self, model_name: str = None, api_key: Optional[str] = None):
        """Initialize the LLM processor.
        
        Args:
            model_name: LiteLLM compatible model string (uses Config.DEFAULT_MODEL if None)
            api_key: Optional API key. LiteLLM typically uses environment variables.
        """
        # Use config default if model_name not provided
        self.model = model_name or Config.DEFAULT_MODEL
        
        # Results directory from config
        self.results_dir = Config.LLM_RESULTS_DIR
        
        log.info(f"Initialized LLMProcessor with model: {self.model}")
        
        # Check for relevant API keys using Config
        api_key_present = bool(Config.get_api_key("anthropic") or 
                              Config.get_api_key("openai") or 
                              Config.get_api_key("google"))
        
        if not api_key_present:
            log.warning("No relevant LLM API key found in environment variables. Will simulate responses for development.")
    
    def _clean_html_content(self, html_content: str) -> str:
        """Clean HTML content by removing script, style, and other non-content elements.
        
        Args:
            html_content: Raw HTML content to clean
            
        Returns:
            Cleaned HTML content as string
        """
        # Use the shared clean_html utility
        return clean_html(html_content)
        
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
        
        # Check for API keys using Config
        api_key_present = bool(Config.get_api_key("anthropic") or 
                              Config.get_api_key("openai") or 
                              Config.get_api_key("google"))
        
        if not api_key_present:
            # Simulate a response for development without API key
            log.warning("Using simulated LLM response (no relevant API key found)")
            raise Exception("No API key found, Add it to the environment variables.")
        
        system_prompt = self.generate_system_prompt()
        
        # Clean the HTML content
        cleaned_html = self._clean_html_content(html_content)
        
        # Ensure cleaned HTML is not excessively long using Config
        if len(cleaned_html) > Config.MAX_HTML_LENGTH:
            log.warning(f"HTML content too long ({len(cleaned_html)} chars), truncating to {Config.MAX_HTML_LENGTH} chars. This might break HTML structure.")
            user_content = cleaned_html[:Config.MAX_HTML_LENGTH]
        else:
            user_content = cleaned_html
        
        llm_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}  # Send structured HTML
        ]
        
        try:
            log.info(f"Calling LLM ({self.model}) via LiteLLM to extract district offices for {bioguide_id}")
            
            # Make the API call using LiteLLM with Config values
            response = litellm.completion(
                model=self.model,
                messages=llm_messages,
                max_tokens=Config.MAX_TOKENS,
                temperature=Config.TEMPERATURE
            )
            
            # Cost Tracking
            try:
                cost = litellm.completion_cost(completion_response=response)
                log.info(f"LLM call cost for {extraction_id}: ${cost:.6f}")
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
            response_path = self.results_dir / f"{extraction_id}_response.txt"
            with open(response_path, 'w', encoding='utf-8') as f:
                f.write(f"Model: {self.model}\n\n{response_text}")
            
            # Save extracted offices for reference
            result_path = self.results_dir / f"{extraction_id}.json"
            with open(result_path, 'w', encoding='utf-8') as f:
                json.dump(result_json, f, indent=2)
            
            log.info(f"Successfully extracted {len(result_json)} district offices for {bioguide_id} using {self.model}")
            return result_json
            
        except litellm.exceptions.APIConnectionError as e:
            log.error(f"LiteLLM API Connection Error: {e}")
            return []
        except litellm.exceptions.RateLimitError as e:
            log.error(f"LiteLLM Rate Limit Error: {e}")
            return []
        except litellm.exceptions.APIError as e:
            log.error(f"LiteLLM API Error: {e}")
            return []
        except Exception as e:
            log.error(f"Failed to extract district offices with LLM ({self.model}): {e}")
            import traceback
            log.error(traceback.format_exc())
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