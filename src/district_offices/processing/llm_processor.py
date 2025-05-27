#!/usr/bin/env python3

import logging
import os
import sys
import json
import time
import random
from typing import Dict, List, Optional, Any

# Import LiteLLM for multi-provider LLM support
import litellm

# Import centralized configuration
from district_offices.config import Config
from district_offices.utils.html import clean_html
from district_offices.utils.url_utils import generate_fallback_urls

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
        db_path = Config.get_sqlite_db_path()
        _sqlite_db = SQLiteDatabase(str(db_path))
    return _sqlite_db

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
        
        log.info(f"Initialized LLMProcessor with model: {self.model}")
        
        # Check for relevant API keys using Config
        api_key_present = bool(Config.get_api_key("anthropic") or 
                              Config.get_api_key("openai") or 
                              Config.get_api_key("gemini"))
        
        if not api_key_present:
            log.warning("No relevant LLM API key found in environment variables. Will simulate responses for development.")
    
    def _exponential_backoff_retry(self, func, max_retries: int = 5, base_delay: float = 1.0):
        """Execute a function with exponential backoff for rate limiting.
        
        Args:
            func: Function to execute
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
            
        Returns:
            Function result if successful
            
        Raises:
            Exception: The last exception encountered if all retries fail
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return func()
            except litellm.exceptions.RateLimitError as e:
                last_exception = e
                if attempt == max_retries:
                    log.error(f"Rate limit exceeded after {max_retries} retries")
                    raise e
                    
                # Calculate delay with exponential backoff and jitter
                delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
                log.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}), waiting {delay:.2f}s before retry")
                time.sleep(delay)
            except Exception as e:
                # For non-rate-limit errors, don't retry
                raise e
        
        # This should never be reached, but just in case
        raise last_exception
    
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

    def extract_district_offices(self, html_content: str, bioguide_id: str, extraction_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Extract district office information from HTML content using the LLM via LiteLLM.
        
        Args:
            html_content: Structured HTML content from the representative's contact page.
            bioguide_id: Bioguide ID for reference.
            extraction_id: Optional extraction ID to associate artifacts with.
            
        Returns:
            List of dictionaries containing extracted district office information.
        """
        # Generate unique ID for logging if extraction_id not provided
        if extraction_id is None:
            extraction_id = f"{bioguide_id}_{int(time.time())}"
        
        # Check for API keys using Config
        api_key_present = bool(Config.get_api_key("anthropic") or 
                              Config.get_api_key("openai") or 
                              Config.get_api_key("gemini"))
        
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
            
            # Define the LLM call function for retry logic
            def make_llm_call():
                return litellm.completion(
                    model=self.model,
                    messages=llm_messages,
                    max_tokens=Config.MAX_TOKENS,
                    temperature=Config.TEMPERATURE,
                    thinking={"type": "enabled", "budget_tokens": 1024} if litellm.supports_reasoning(model=self.model) else None
                )
            
            # Make the API call using LiteLLM with exponential backoff for rate limits
            response = self._exponential_backoff_retry(make_llm_call)
            
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
            
            # Save the full response and extracted offices as artifacts if we have an extraction_id
            if extraction_id:
                db = _get_sqlite_db()
                
                # Store raw LLM response
                db.store_artifact(
                    extraction_id=extraction_id,
                    artifact_type='llm_response',
                    filename=f"{bioguide_id}_{int(time.time())}_llm_response.txt",
                    content=f"Model: {self.model}\n\n{response_text}".encode('utf-8'),
                    content_type='text/plain'
                )
                
                # Store extracted offices JSON
                db.store_artifact(
                    extraction_id=extraction_id,
                    artifact_type='extracted_offices',
                    filename=f"{bioguide_id}_{int(time.time())}_offices.json",
                    content=json.dumps(result_json, indent=2).encode('utf-8'),
                    content_type='application/json'
                )
            
            log.info(f"Successfully extracted {len(result_json)} district offices for {bioguide_id} using {self.model}")
            return result_json
            
        except litellm.exceptions.APIConnectionError as e:
            log.error(f"LiteLLM API Connection Error: {e}")
            return []
        except litellm.exceptions.RateLimitError as e:
            # This should be handled by the exponential backoff, but if it gets here
            # it means all retries were exhausted
            log.error(f"LiteLLM Rate Limit Error after all retries exhausted: {e}")
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

    def extract_district_offices_with_fallbacks(
        self, 
        primary_url: str, 
        bioguide_id: str, 
        extraction_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Extract district offices trying primary URL first, then fallbacks if 0 results.
        
        This method implements a loop-based approach that tries the primary URL first,
        and if no offices are extracted, automatically tries fallback URLs until
        offices are found or all URLs are exhausted.
        
        Args:
            primary_url: The primary contact page URL to try first
            bioguide_id: Bioguide ID for reference and logging
            extraction_id: Optional extraction ID to associate artifacts with
            
        Returns:
            List of dictionaries containing extracted district office information
        """
        # Build URL queue: primary first, then fallbacks
        urls_to_try = [primary_url] + generate_fallback_urls(primary_url)
        
        log.info(f"Starting extraction for {bioguide_id} with {len(urls_to_try)} URLs to try")
        
        for i, url in enumerate(urls_to_try):
            is_fallback = i > 0
            attempt_type = "fallback" if is_fallback else "primary"
            
            log.info(f"Attempting {attempt_type} URL ({i+1}/{len(urls_to_try)}): {url}")
            
            # Use existing scraper infrastructure for HTML extraction
            from district_offices.core.scraper import extract_html
            html_content, artifact_ref = extract_html(url, extraction_id=extraction_id)
            
            if not html_content:
                log.warning(f"Failed to fetch HTML from {attempt_type} URL: {url} (likely HTTP error)")
                continue
            
            log.info(f"Successfully fetched HTML from {attempt_type} URL: {url}")
            
            # Use existing LLM extraction method (reuses all the existing logic)
            offices = self.extract_district_offices(html_content, bioguide_id, extraction_id)
            
            if offices:
                log.info(f"Successfully extracted {len(offices)} offices from {attempt_type} URL: {url}")
                
                # Store additional metadata about successful URL if it was a fallback
                if is_fallback and extraction_id:
                    db = _get_sqlite_db()
                    
                    # Store fallback success metadata
                    db.store_artifact(
                        extraction_id=extraction_id,
                        artifact_type='fallback_metadata',
                        filename=f"{bioguide_id}_{int(time.time())}_fallback_success.json",
                        content=json.dumps({
                            "original_url": primary_url,
                            "successful_url": url,
                            "attempt_number": i + 1,
                            "total_attempts": len(urls_to_try),
                            "offices_found": len(offices)
                        }, indent=2).encode('utf-8'),
                        content_type='application/json'
                    )
                
                return offices
            else:
                log.info(f"0 offices extracted from {attempt_type} URL: {url}")
        
        log.warning(f"No offices found in primary URL or any of the {len(urls_to_try)-1} fallback URLs for {bioguide_id}")
        
        # Store failure metadata if we have extraction_id
        if extraction_id:
            db = _get_sqlite_db()
            
            db.store_artifact(
                extraction_id=extraction_id,
                artifact_type='fallback_failure',
                filename=f"{bioguide_id}_{int(time.time())}_fallback_failure.json",
                content=json.dumps({
                    "primary_url": primary_url,
                    "fallback_urls": urls_to_try[1:],
                    "total_attempts": len(urls_to_try),
                    "reason": "No offices found in any URL"
                }, indent=2).encode('utf-8'),
                content_type='application/json'
            )
        
        return []