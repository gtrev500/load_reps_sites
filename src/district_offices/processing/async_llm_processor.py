#!/usr/bin/env python3
"""Async LLM processor for extracting district office information."""

import logging
import os
import json
import time
import asyncio
import aiofiles
from typing import Dict, List, Optional, Any
import litellm
from litellm import acompletion  # Async completion

log = logging.getLogger(__name__)


class AsyncLLMProcessor:
    """Async class for processing HTML content using LiteLLM."""
    
    def __init__(self, model_name: str = "claude-3-haiku-20240307", api_key: Optional[str] = None):
        """Initialize the async LLM processor.
        
        Args:
            model_name: LiteLLM compatible model string
            api_key: Optional API key
        """
        self.model = model_name
        
        # Set API key if provided
        if api_key:
            if "claude" in model_name.lower():
                os.environ["ANTHROPIC_API_KEY"] = api_key
            elif "gpt" in model_name.lower():
                os.environ["OPENAI_API_KEY"] = api_key
        
        # Configure litellm
        litellm.drop_params = True
        litellm.set_verbose = False
        
        # Cache directory for LLM responses
        self.cache_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "cache", "llm_results"
        )
        os.makedirs(self.cache_dir, exist_ok=True)
    
    async def extract_district_offices(
        self, 
        html_sections: List[str], 
        bioguide_id: str,
        use_cache: bool = True
    ) -> Optional[List[Dict[str, Any]]]:
        """Extract district office information from HTML sections using async LLM.
        
        Args:
            html_sections: List of HTML sections to process
            bioguide_id: Bioguide ID for the representative
            use_cache: Whether to use cached results
            
        Returns:
            List of extracted office dictionaries or None if failed
        """
        # Check cache first
        if use_cache:
            cached_result = await self._load_cached_result(bioguide_id)
            if cached_result:
                return cached_result
        
        # Prepare the prompt
        prompt = self._create_extraction_prompt(html_sections)
        
        try:
            # Make async API call
            response = await acompletion(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that extracts structured district office information from HTML content."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=4000
            )
            
            # Extract the response
            result_text = response.choices[0].message.content
            
            # Save raw response
            await self._save_raw_response(bioguide_id, result_text)
            
            # Parse the JSON response
            offices = self._parse_llm_response(result_text)
            
            if offices:
                # Add bioguide_id to each office
                for office in offices:
                    office['bioguide_id'] = bioguide_id
                
                # Cache the result
                await self._cache_result(bioguide_id, offices)
                
                return offices
            else:
                log.error(f"Failed to parse LLM response for {bioguide_id}")
                return None
                
        except Exception as e:
            log.error(f"Error calling LLM API: {e}")
            return None
    
    def _create_extraction_prompt(self, html_sections: List[str]) -> str:
        """Create the prompt for the LLM."""
        sections_text = "\n\n---\n\n".join(html_sections[:5])  # Limit to 5 sections
        
        return f"""Extract all district office information from the following HTML sections. 
Look for office addresses, phone numbers, fax numbers, and office hours.

Return the information as a JSON array with the following structure:
{{
  "offices": [
    {{
      "office_type": "District Office" or "Main Office" or "Satellite Office",
      "address": "street address",
      "suite": "suite or room number if mentioned separately",
      "building": "building name if mentioned",
      "city": "city name",
      "state": "state abbreviation (2 letters)",
      "zip": "zip code",
      "phone": "phone number",
      "fax": "fax number if available",
      "hours": "office hours if available",
      "notes": "any other relevant information"
    }}
  ]
}}

Important:
- Extract ALL district offices mentioned, not just the first one
- Use null for any fields that are not found
- Ensure state is a 2-letter abbreviation
- Phone and fax should include area code
- Do not make up information that isn't in the HTML

HTML sections to analyze:

{sections_text}

Return ONLY the JSON object, no other text."""
    
    def _parse_llm_response(self, response_text: str) -> Optional[List[Dict[str, Any]]]:
        """Parse the LLM response to extract office data."""
        try:
            # Try to find JSON in the response
            response_text = response_text.strip()
            
            # Look for JSON between ```json and ``` markers
            if "```json" in response_text:
                start = response_text.find("```json") + 7
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            elif "```" in response_text:
                start = response_text.find("```") + 3
                end = response_text.find("```", start)
                response_text = response_text[start:end].strip()
            
            # Parse JSON
            data = json.loads(response_text)
            
            # Extract offices array
            if isinstance(data, dict) and "offices" in data:
                offices = data["offices"]
            elif isinstance(data, list):
                offices = data
            else:
                log.error("Unexpected response format")
                return None
            
            # Validate and clean each office
            cleaned_offices = []
            for office in offices:
                if isinstance(office, dict) and "address" in office:
                    # Generate office_id
                    office_id = self._generate_office_id(office)
                    office['office_id'] = office_id
                    
                    # Set default office_type if missing
                    if 'office_type' not in office or not office['office_type']:
                        office['office_type'] = 'District Office'
                    
                    cleaned_offices.append(office)
            
            return cleaned_offices if cleaned_offices else None
            
        except json.JSONDecodeError as e:
            log.error(f"Failed to parse JSON response: {e}")
            log.debug(f"Response text: {response_text}")
            return None
        except Exception as e:
            log.error(f"Error parsing LLM response: {e}")
            return None
    
    def _generate_office_id(self, office: Dict[str, Any]) -> str:
        """Generate a unique office ID based on address."""
        # Use address, city, state, zip to create ID
        parts = []
        for field in ['address', 'city', 'state', 'zip']:
            if field in office and office[field]:
                parts.append(str(office[field]).lower().replace(' ', '_'))
        
        return '_'.join(parts)[:100]  # Limit length
    
    async def _load_cached_result(self, bioguide_id: str) -> Optional[List[Dict[str, Any]]]:
        """Load cached result if available."""
        cache_file = os.path.join(self.cache_dir, f"{bioguide_id}_latest.json")
        
        if os.path.exists(cache_file):
            try:
                async with aiofiles.open(cache_file, 'r') as f:
                    data = json.loads(await f.read())
                log.info(f"Using cached LLM result for {bioguide_id}")
                return data
            except Exception as e:
                log.error(f"Error loading cached result: {e}")
        
        return None
    
    async def _cache_result(self, bioguide_id: str, offices: List[Dict[str, Any]]):
        """Cache the extraction result."""
        # Save with timestamp
        timestamp = int(time.time())
        cache_file = os.path.join(self.cache_dir, f"{bioguide_id}_{timestamp}.json")
        
        try:
            async with aiofiles.open(cache_file, 'w') as f:
                await f.write(json.dumps(offices, indent=2))
            
            # Also save as latest
            latest_file = os.path.join(self.cache_dir, f"{bioguide_id}_latest.json")
            async with aiofiles.open(latest_file, 'w') as f:
                await f.write(json.dumps(offices, indent=2))
                
        except Exception as e:
            log.error(f"Error caching result: {e}")
    
    async def _save_raw_response(self, bioguide_id: str, response_text: str):
        """Save the raw LLM response for debugging."""
        timestamp = int(time.time())
        response_file = os.path.join(
            self.cache_dir, 
            f"{bioguide_id}_{timestamp}_response.txt"
        )
        
        try:
            async with aiofiles.open(response_file, 'w') as f:
                await f.write(response_text)
        except Exception as e:
            log.error(f"Error saving raw response: {e}")


# Backward compatibility wrapper
async def extract_district_offices_async(
    html_sections: List[str],
    bioguide_id: str,
    model_name: str = "claude-3-haiku-20240307",
    api_key: Optional[str] = None,
    use_cache: bool = True
) -> Optional[List[Dict[str, Any]]]:
    """Convenience function for async extraction.
    
    Args:
        html_sections: List of HTML sections to process
        bioguide_id: Bioguide ID for the representative
        model_name: LLM model to use
        api_key: Optional API key
        use_cache: Whether to use cached results
        
    Returns:
        List of extracted office dictionaries or None if failed
    """
    processor = AsyncLLMProcessor(model_name, api_key)
    return await processor.extract_district_offices(html_sections, bioguide_id, use_cache)