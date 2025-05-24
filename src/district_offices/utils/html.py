"""HTML processing utilities."""

import logging
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

def clean_html(html_content: str) -> str:
    """Clean HTML content by removing scripts, styles, and path tags.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        Cleaned HTML content
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script, style, and path elements
        for tag in soup(["script", "style", "path", "svg"]):
            tag.decompose()
            
        # Get cleaned HTML (pretty print for readability)
        cleaned_html = soup.prettify()
        log.debug("Successfully cleaned HTML content")
        return cleaned_html
    except Exception as e:
        log.error(f"Failed to clean HTML: {e}")
        return html_content  # Return original content if cleaning fails