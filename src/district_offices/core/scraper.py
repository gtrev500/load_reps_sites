#!/usr/bin/env python3

import logging
import os
import sys
import requests
import time
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



