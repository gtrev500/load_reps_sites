#!/usr/bin/env python3
"""Async web scraping module using aiohttp and playwright."""

import logging
import os
import hashlib
import json
import asyncio
from typing import Dict, Optional, Tuple, List
from urllib.parse import urljoin
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

log = logging.getLogger(__name__)

# Constants
REQUEST_TIMEOUT = 30
USER_AGENT = "Mozilla/5.0 (compatible; DistrictOfficeScraper/1.0)"
HTML_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "cache", "html")
IMAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "cache", "screenshots")

# Ensure cache directories exist
os.makedirs(HTML_CACHE_DIR, exist_ok=True)
os.makedirs(IMAGE_DIR, exist_ok=True)


async def extract_html(url: str, use_cache: bool = True) -> Tuple[Optional[str], Optional[str]]:
    """Extract HTML content from a URL asynchronously.
    
    Args:
        url: The URL to extract HTML from
        use_cache: Whether to use cached HTML if available
        
    Returns:
        Tuple of (html_content, cache_path)
    """
    # Generate cache filename
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_path = os.path.join(HTML_CACHE_DIR, f"{url_hash}.html")
    
    # Check cache first
    if use_cache and os.path.exists(cache_path):
        log.info(f"Using cached HTML for {url}")
        async with aiofiles.open(cache_path, 'r', encoding='utf-8') as f:
            html_content = await f.read()
        return html_content, cache_path
    
    # Fetch fresh HTML
    log.info(f"Fetching HTML from {url}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                headers={'User-Agent': USER_AGENT}
            ) as response:
                response.raise_for_status()
                html_content = await response.text()
        
        # Save to cache
        async with aiofiles.open(cache_path, 'w', encoding='utf-8') as f:
            await f.write(html_content)
        
        return html_content, cache_path
        
    except aiohttp.ClientError as e:
        log.error(f"Error fetching HTML from {url}: {e}")
        return None, None
    except Exception as e:
        log.error(f"Unexpected error fetching HTML: {e}")
        return None, None


def clean_html(html_content: str) -> str:
    """Clean HTML content by removing scripts, styles, and comments.
    
    This is a synchronous function as BeautifulSoup operations are CPU-bound.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        Cleaned HTML content
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()
    
    # Remove comments
    for comment in soup.find_all(string=lambda text: isinstance(text, str) and text.strip().startswith('<!--')):
        comment.extract()
    
    # Get text with preserved structure
    return str(soup)


def extract_contact_sections(html_content: str, max_sections: int = 5) -> List[str]:
    """Extract relevant contact sections from HTML.
    
    This is a synchronous function as BeautifulSoup operations are CPU-bound.
    
    Args:
        html_content: HTML content to extract from
        max_sections: Maximum number of sections to extract
        
    Returns:
        List of extracted HTML sections
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    sections = []
    
    # Keywords that indicate contact information
    contact_keywords = [
        'district office', 'office location', 'contact', 'address',
        'phone', 'fax', 'hours', 'office hours'
    ]
    
    # Find sections containing contact keywords
    for keyword in contact_keywords:
        # Search in headers
        for header in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            if keyword.lower() in header.text.lower():
                # Get the parent container
                parent = header.parent
                while parent and parent.name in ['a', 'span', 'strong', 'em']:
                    parent = parent.parent
                
                if parent and str(parent) not in sections:
                    sections.append(str(parent))
                    if len(sections) >= max_sections:
                        return sections
        
        # Search in divs with specific classes/ids
        for div in soup.find_all(['div', 'section', 'article']):
            div_text = div.text.lower()
            div_attrs = str(div.attrs).lower()
            
            if keyword in div_text or keyword in div_attrs:
                if str(div) not in sections:
                    sections.append(str(div))
                    if len(sections) >= max_sections:
                        return sections
    
    # If we didn't find enough sections, look for address-like patterns
    if len(sections) < max_sections:
        # Find elements that look like addresses
        for elem in soup.find_all(text=True):
            text = elem.strip()
            # Simple heuristic: contains state abbreviation and zip code pattern
            if len(text) > 20 and any(state in text for state in [' AL ', ' AK ', ' AZ ', ' AR ', ' CA ', ' CO ', ' CT ', ' DE ', ' FL ', ' GA ', ' HI ', ' ID ', ' IL ', ' IN ', ' IA ', ' KS ', ' KY ', ' LA ', ' ME ', ' MD ', ' MA ', ' MI ', ' MN ', ' MS ', ' MO ', ' MT ', ' NE ', ' NV ', ' NH ', ' NJ ', ' NM ', ' NY ', ' NC ', ' ND ', ' OH ', ' OK ', ' OR ', ' PA ', ' RI ', ' SC ', ' SD ', ' TN ', ' TX ', ' UT ', ' VT ', ' VA ', ' WA ', ' WV ', ' WI ', ' WY ']):
                parent = elem.parent
                while parent and parent.name in ['a', 'span', 'strong', 'em']:
                    parent = parent.parent
                
                if parent and str(parent) not in sections:
                    sections.append(str(parent))
                    if len(sections) >= max_sections:
                        return sections
    
    return sections


async def capture_screenshot(url: str, output_path: Optional[str] = None) -> Optional[str]:
    """Capture a screenshot of a webpage using Playwright.
    
    Args:
        url: URL to capture
        output_path: Optional path to save screenshot
        
    Returns:
        Path to saved screenshot or None if failed
    """
    if output_path is None:
        url_hash = hashlib.md5(url.encode()).hexdigest()
        output_path = os.path.join(IMAGE_DIR, f"{url_hash}.png")
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Set viewport and user agent
            await page.set_viewport_size({"width": 1920, "height": 1080})
            await page.set_extra_http_headers({"User-Agent": USER_AGENT})
            
            # Navigate to page
            await page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
            
            # Wait a bit for dynamic content
            await asyncio.sleep(2)
            
            # Capture screenshot
            await page.screenshot(path=output_path, full_page=True)
            
            await browser.close()
            
        log.info(f"Screenshot saved to {output_path}")
        return output_path
        
    except Exception as e:
        log.error(f"Error capturing screenshot: {e}")
        return None


async def extract_with_playwright(url: str) -> Optional[str]:
    """Extract HTML content using Playwright for JavaScript-heavy sites.
    
    Args:
        url: URL to extract from
        
    Returns:
        HTML content or None if failed
    """
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            # Set user agent
            await page.set_extra_http_headers({"User-Agent": USER_AGENT})
            
            # Navigate to page
            await page.goto(url, wait_until="networkidle", timeout=REQUEST_TIMEOUT * 1000)
            
            # Wait for potential dynamic content
            await asyncio.sleep(2)
            
            # Get page content
            content = await page.content()
            
            await browser.close()
            
        return content
        
    except Exception as e:
        log.error(f"Error extracting with Playwright: {e}")
        return None