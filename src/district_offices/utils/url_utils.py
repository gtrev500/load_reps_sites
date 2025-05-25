#!/usr/bin/env python3

"""URL utilities for generating fallback URLs and handling URL patterns."""

import logging
from urllib.parse import urlparse, urljoin
from typing import List

log = logging.getLogger(__name__)

def get_base_url(contact_url: str) -> str:
    """Extract base URL from contact page URL.
    
    Args:
        contact_url: The original contact page URL
        
    Returns:
        Base URL (scheme + netloc + /)
        
    Example:
        get_base_url("https://example.house.gov/contact") -> "https://example.house.gov/"
    """
    parsed = urlparse(contact_url)
    return f"{parsed.scheme}://{parsed.netloc}/"

def generate_fallback_urls(contact_url: str) -> List[str]:
    """Generate ordered list of fallback URLs to try when primary contact page fails.
    
    This function generates common URL patterns where congressional district offices
    are typically listed on representative websites.
    
    Args:
        contact_url: The original contact page URL that failed
        
    Returns:
        List of fallback URLs to try, ordered by likelihood of success
        
    Example:
        generate_fallback_urls("https://example.house.gov/contact") ->
        [
            "https://example.house.gov/",
            "https://example.house.gov/offices",
            "https://example.house.gov/locations",
            "https://example.house.gov/district-offices",
            "https://example.house.gov/office-locations",
            "https://example.house.gov/local-offices"
        ]
    """
    base_url = get_base_url(contact_url)
    
    # Common patterns for district office pages on congressional websites
    # Ordered by likelihood of success based on observed patterns
    fallback_paths = [
        "",  # Root/home page - often has office info
        "offices",  # Most common pattern
        "contact/district-offices",  # More specific but common
        "locations",  # Second most common
        "office-locations",  # Variation of locations
        "local-offices",  # Alternative phrasing
        "contact-us",  # Alternative contact page format
        "services",  # Sometimes offices listed under services
        "about",  # About pages sometimes have office info
    ]
    
    fallback_urls = []
    for path in fallback_paths:
        url = urljoin(base_url, path)
        # Don't duplicate the original URL
        if url != contact_url:
            fallback_urls.append(url)
    
    log.debug(f"Generated {len(fallback_urls)} fallback URLs for {contact_url}")
    return fallback_urls