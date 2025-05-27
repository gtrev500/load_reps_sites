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

def extract_html(url: str, use_cache: bool = True, extraction_id: Optional[int] = None) -> Tuple[Optional[str], Optional[str]]:
    """Extract HTML content from a URL.
    
    Args:
        url: The URL to extract HTML from
        use_cache: Whether to use cached HTML if available
        extraction_id: Optional extraction ID to associate the artifact with
        
    Returns:
        A tuple of (html_content, artifact_identifier) or (None, None) if extraction fails
    """
    db = _get_sqlite_db()
    
    # Check cache first if enabled
    if use_cache:
        cached_content = db.get_cached_content(url, 'html')
        if cached_content:
            log.info(f"Using cached HTML for {url}")
            return cached_content, f"cache:{url}"
    
    # Make the request
    headers = {
        "User-Agent": Config.USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml",
    }
    
    try:
        log.info(f"Fetching HTML from {url}")
        response = requests.get(url, headers=headers, timeout=Config.REQUEST_TIMEOUT, allow_redirects=True)
        
        # Check if we were redirected to a different host
        if response.url != url:
            from urllib.parse import urlparse
            original_host = urlparse(url).netloc
            final_host = urlparse(response.url).netloc
            
            if original_host != final_host:
                log.warning(f"Redirect to different host blocked: {url} -> {response.url}")
                return None, None
            else:
                log.info(f"Redirected within same host: {url} -> {response.url}")
        
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        html_content = response.text
        
        # Store in cache
        db.store_cache_entry(url, 'html', html_content)
        
        # If we have an extraction_id, also store as an artifact
        artifact_id = None
        if extraction_id:
            artifact_id = db.store_artifact(
                extraction_id=extraction_id,
                artifact_type='html',
                filename=f"{hashlib.md5(url.encode()).hexdigest()}.html",
                content=html_content.encode('utf-8'),
                content_type='text/html'
            )
            log.info(f"Stored HTML as artifact {artifact_id} for extraction {extraction_id}")
        
        log.info(f"Successfully fetched HTML from {url}")
        return html_content, f"artifact:{artifact_id}" if artifact_id else f"cache:{url}"
        
    except requests.exceptions.RequestException as e:
        log.error(f"Failed to fetch HTML from {url}: {e}")
        return None, None
    except Exception as e:
        log.error(f"Unexpected error fetching HTML from {url}: {e}")
        return None, None

def capture_screenshot(html_content: str, bioguide_id: str, extraction_id: Optional[int] = None) -> Optional[str]:
    """Capture a screenshot of the HTML content for visual reference.
    
    In a complete implementation, this would render the HTML and take a screenshot.
    For this prototype, we'll save the HTML content as a reference artifact.
    
    Args:
        html_content: HTML content to capture
        bioguide_id: Bioguide ID for reference
        extraction_id: Optional extraction ID to associate the artifact with
        
    Returns:
        Artifact identifier or None if capture fails
    """
    # In a real implementation, this might use a headless browser to render a screenshot
    # For this prototype, we'll store the HTML as a "screenshot" artifact
    
    if not extraction_id:
        log.warning("No extraction_id provided for screenshot, skipping storage")
        return None
    
    db = _get_sqlite_db()
    timestamp = int(time.time())
    
    try:
        artifact_id = db.store_artifact(
            extraction_id=extraction_id,
            artifact_type='screenshot',
            filename=f"{bioguide_id}_{timestamp}_screenshot.html",
            content=html_content.encode('utf-8'),
            content_type='text/html'
        )
        
        log.info(f"Saved HTML screenshot as artifact {artifact_id} for {bioguide_id}")
        return f"artifact:{artifact_id}"
    except Exception as e:
        log.error(f"Failed to save HTML screenshot for {bioguide_id}: {e}")
        return None



