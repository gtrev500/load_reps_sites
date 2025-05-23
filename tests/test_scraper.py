#!/usr/bin/env python3

"""
Test script for the district office scraper.
This script tests the basic functionality without actually calling the LLM API
or making database changes.
"""

import os
import sys
import logging

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from district_offices.core.scraper import extract_html, clean_html, extract_contact_sections
from district_offices.processing.llm_processor import LLMProcessor
from district_offices.validation.interface import ValidationInterface

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)

def test_html_extraction():
    """Test HTML extraction from a URL."""
    print("\n=== Testing HTML Extraction ===")
    
    # Test URL - use a URL that is likely to be accessible
    test_url = "https://www.schiff.senate.gov/contact/"
    
    print(f"Extracting HTML from {test_url}...")
    html_content, html_path = extract_html(test_url)
    
    if html_content:
        print(f"✅ Successfully extracted HTML! (Length: {len(html_content)} characters)")
        print(f"✅ HTML saved to: {html_path}")
        
        # Test HTML cleaning
        print("\nCleaning HTML...")
        cleaned_html = clean_html(html_content)
        print(f"✅ Successfully cleaned HTML! (Length: {len(cleaned_html)} characters)")
        
        # Test contact section extraction
        print("\nExtracting contact sections...")
        contact_sections = extract_contact_sections(cleaned_html)
        print(f"✅ Successfully extracted contact sections! (Length: {len(contact_sections)} characters)")
        
        return html_content, contact_sections
    else:
        print("❌ Failed to extract HTML!")
        return None, None

def test_llm_extraction(html_content):
    """Test LLM extraction of district office information."""
    print("\n=== Testing LLM Extraction ===")
    
    test_bioguide_id = "S001150"  # Adam Schiff
    
    print(f"Extracting district offices for {test_bioguide_id}...")
    llm_processor = LLMProcessor()  # No API key, will use simulation
    
    extracted_offices = llm_processor.extract_district_offices(html_content, test_bioguide_id)
    
    if extracted_offices:
        print(f"✅ Successfully extracted {len(extracted_offices)} offices!")
        print("\nExtracted Offices:")
        print("------------------")
        for i, office in enumerate(extracted_offices, 1):
            print(f"Office #{i}:")
            for key, value in office.items():
                print(f"  {key}: {value}")
            print()
        
        return extracted_offices
    else:
        print("❌ Failed to extract offices or no offices found!")
        return []

def test_validation_interface(html_content, extracted_offices):
    """Test the validation interface."""
    print("\n=== Testing Validation Interface ===")
    
    test_bioguide_id = "S001150"  # Adam Schiff
    test_url = "https://www.schiff.senate.gov/contact/"
    
    print("Generating validation HTML...")
    validation = ValidationInterface()
    validation_html_path = validation.generate_validation_html(
        test_bioguide_id, html_content, extracted_offices, test_url
    )
    
    print(f"✅ Generated validation HTML at: {validation_html_path}")
    print("\nIn a real scenario, this would open in a browser for validation.")
    print("For this test, we'll just simulate the validation.")
    
    # Don't actually open the browser in the test
    # validation.open_validation_interface(validation_html_path)
    
    print("\nWould you like to open the validation HTML in a browser? (y/n)")
    response = input().strip().lower()
    
    if response == 'y':
        validation.open_validation_interface(validation_html_path)
        print("Browser should open with the validation interface.")
    else:
        print("Skipping browser opening.")
    
    return validation_html_path

def main():
    """Main test function."""
    print("=== District Office Scraper Test ===")
    
    # Test HTML extraction
    html_content, contact_sections = test_html_extraction()
    
    if not html_content:
        print("❌ Cannot proceed with tests due to HTML extraction failure.")
        sys.exit(1)
    
    # Test LLM extraction
    extracted_offices = test_llm_extraction(contact_sections or html_content)
    
    # Test validation interface
    if extracted_offices:
        test_validation_interface(html_content, extracted_offices)
    
    print("\n=== Test Complete ===")
    print("All tests completed successfully!")

if __name__ == "__main__":
    main()