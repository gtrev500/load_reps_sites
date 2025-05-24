#!/usr/bin/env python3

import logging
import os
import sys
import requests
import time
from bs4 import BeautifulSoup
from typing import Dict, Optional, Tuple
from urllib.parse import urljoin
import hashlib
import json

# Import centralized configuration
from district_offices.config import Config

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

def extract_html(url: str, use_cache: bool = True) -> Tuple[Optional[str], Optional[str]]:
    """Extract HTML content from a URL.
    
    Args:
        url: The URL to extract HTML from
        use_cache: Whether to use cached HTML if available
        
    Returns:
        A tuple of (html_content, cache_path) or (None, None) if extraction fails
    """
    # Generate a filename for caching based on the URL
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_path = Config.HTML_CACHE_DIR / f"{url_hash}.html"
    
    # Check if we have a cached version
    if use_cache and cache_path.exists():
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                log.info(f"Using cached HTML for {url}")
                return f.read(), str(cache_path)
        except Exception as e:
            log.warning(f"Failed to read cached HTML for {url}: {e}")
    
    # Make the request
    headers = {
        "User-Agent": Config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml",
    }
    
    try:
        log.info(f"Fetching HTML from {url}")
        response = requests.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Save to cache
        with open(cache_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        
        log.info(f"Successfully fetched HTML from {url}")
        return response.text, str(cache_path)
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to fetch HTML from {url}: {e}")
        return None, None
    except Exception as e:
        log.error(f"Unexpected error fetching HTML from {url}: {e}")
        return None, None

def capture_screenshot(html_path: str, bioguide_id: str) -> Optional[str]:
    """Capture a screenshot of the HTML content for visual reference.
    
    In a complete implementation, this would render the HTML and take a screenshot.
    For this prototype, we'll save the HTML content as a reference.
    
    Args:
        html_path: Path to the HTML file
        bioguide_id: Bioguide ID for reference
        
    Returns:
        Path to the screenshot or None if capture fails
    """
    # In a real implementation, this might use a headless browser to render a screenshot
    # For this prototype, we'll just copy the HTML file with a different name
    timestamp = int(time.time())
    screenshot_path = Config.SCREENSHOT_DIR / f"{bioguide_id}_{timestamp}.html"
    
    try:
        with open(html_path, 'r', encoding='utf-8') as src:
            html_content = src.read()
            
        with open(screenshot_path, 'w', encoding='utf-8') as dest:
            dest.write(html_content)
            
        log.info(f"Saved HTML reference for {bioguide_id}")
        return str(screenshot_path)
    except Exception as e:
        log.error(f"Failed to save HTML reference for {bioguide_id}: {e}")
        return None

def clean_html(html_content: str) -> str:
    """Clean HTML content to make it more suitable for extraction.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        Cleaned HTML content
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style elements
        for script in soup(["script", "style", "path"]):
            script.decompose()
            
        # Get cleaned text
        cleaned_html = soup.prettify()
        log.info("Successfully cleaned HTML content")
        return cleaned_html
    except Exception as e:
        log.error(f"Failed to clean HTML: {e}")
        return html_content  # Return original content if cleaning fails

def extract_contact_sections(html_content: str) -> str:
    """Extract sections likely to contain district office information.
    
    This function uses heuristics to identify sections of the HTML that are
    likely to contain district office contact information.
    
    Args:
        html_content: HTML content to extract from
        
    Returns:
        String containing relevant HTML sections
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        contact_sections = []
        
        # Get contact keywords from config
        keywords = Config.get_contact_keywords()
        
        # Look for common container elements that might contain office locations
        for keyword in keywords:
            # Case 1: Elements with keyword in id, class, or text
            elements = soup.find_all(lambda tag: (
                tag.name in ['div', 'section', 'article', 'footer', 'aside'] and
                (
                    (tag.has_attr('id') and keyword in tag['id'].lower()) or
                    (tag.has_attr('class') and any(keyword in c.lower() for c in tag['class'])) or
                    (tag.string and keyword in tag.string.lower())
                )
            ))
            
            # Add elements to contact sections
            for elem in elements:
                elem_str = str(elem)
                if elem_str not in contact_sections:
                    contact_sections.append(elem_str)
        
        # Case 2: Headers that might indicate district office sections  
        for keyword in ['office', 'location', 'contact']:
            header_elements = soup.find_all(
                ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'], 
                text=lambda t: t and keyword in t.lower()
            )
            
            for header in header_elements:
                # Get the header and its next sibling content
                section = str(header)
                sibling = header.find_next_sibling()
                if sibling:
                    section += str(sibling)
                if section not in contact_sections:
                    contact_sections.append(section)
        
        # Join the contact sections
        result = "\n".join(contact_sections)
        log.info(f"Extracted {len(contact_sections)} potential contact sections")
        return result
    except Exception as e:
        log.error(f"Failed to extract contact sections: {e}")
        return html_content  # Return original content if extraction fails

def save_extraction_metadata(
    bioguide_id: str, 
    url: str, 
    html_path: str, 
    screenshot_path: str, 
    extracted_sections: str
) -> str:
    """Save metadata about the extraction process for provenance tracking.
    
    Args:
        bioguide_id: The bioguide ID being processed
        url: The URL that was scraped
        html_path: Path to the cached HTML file
        screenshot_path: Path to the screenshot file
        extracted_sections: The extracted contact sections
        
    Returns:
        Path to the saved metadata file
    """
    metadata = {
        "bioguide_id": bioguide_id,
        "url": url,
        "html_path": html_path,
        "screenshot_path": screenshot_path,
        "extraction_timestamp": time.time(),
        "extraction_date": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    # Save extracted sections to a separate file
    sections_path = os.path.join(os.path.dirname(html_path), f"{bioguide_id}_sections.html")
    with open(sections_path, 'w', encoding='utf-8') as f:
        f.write(extracted_sections)
    
    metadata["extracted_sections_path"] = sections_path
    
    # Save metadata to a JSON file
    metadata_path = os.path.join(os.path.dirname(html_path), f"{bioguide_id}_metadata.json")
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    log.info(f"Saved extraction metadata for {bioguide_id}")
    return metadata_path