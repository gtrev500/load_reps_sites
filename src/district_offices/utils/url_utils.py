#!/usr/bin/env python3

"""URL utilities for generating fallback URLs and handling URL patterns."""

import logging
from urllib.parse import urlparse, urljoin
from typing import List

log = logging.getLogger(__name__)

def get_base_url(url: str) -> str:
    """Extract base URL from any URL.
    
    Args:
        url: Any URL (can be base URL or a page URL)
        
    Returns:
        Base URL (scheme + netloc + /)
        
    Example:
        get_base_url("https://example.house.gov/contact") -> "https://example.house.gov/"
        get_base_url("https://example.house.gov") -> "https://example.house.gov/"
    """
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"

def generate_fallback_urls(base_website_url: str) -> List[str]:
    """Generate ordered list of URLs to try for finding district offices.
    
    This function generates common URL patterns where congressional district offices
    are typically listed on representative websites. Now works with base website URLs
    instead of assuming a /contact starting point.
    
    Args:
        base_website_url: The representative's official website URL
        
    Returns:
        List of URLs to try, ordered by likelihood of success
        
    Example:
        generate_fallback_urls("https://example.house.gov") ->
        [
            "https://example.house.gov/contact",
            "https://example.house.gov/offices", 
            "https://example.house.gov/contact/district-offices",
            "https://example.house.gov/locations",
            "https://example.house.gov/contact/offices",
            "https://example.house.gov/office-locations",
            "https://example.house.gov/contact/locations",
            "https://example.house.gov/contact-us",
            "https://example.house.gov/about",
            "https://example.house.gov/"
        ]
    """
    base_url = get_base_url(base_website_url)
    
    # Common patterns for district office pages on congressional websites
    # Ordered by likelihood of success based on observed patterns
    # Now includes /contact as the first option since we're starting from base URL
    fallback_paths = [
        "",  # Most common contact page
        "public",
        "offices",  # Most common pattern for offices
        "contact/district-offices",  # More specific but common
        "locations",  # Second most common
        "contact/offices",  # Contact page subsection
        "office-locations",  # Variation of locations
        "contact/locations",  # Alternative phrasing
        "contact-us",  # Alternative contact page format
        "about",  # About pages sometimes have office info
    ]
    
    fallback_urls = []
    for path in fallback_paths:
        url = urljoin(base_url, path)
        fallback_urls.append(url)
    
    log.debug(f"Generated {len(fallback_urls)} URLs to try for {base_website_url}")
    return fallback_urls