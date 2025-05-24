#!/usr/bin/env python3
"""Test the complete scraping workflow with SQLite backend."""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from district_offices import (
    get_bioguides_without_district_offices,
    get_contact_page_url,
    Config
)
from district_offices.storage.sqlite_db import SQLiteDatabase
from district_offices.storage.models import Member, MemberContact

def main():
    """Test the scraping workflow."""
    print("Testing Scraping Workflow with SQLite Backend")
    print("=" * 50)
    
    # Get database URI
    db_uri = os.environ.get("DATABASE_URI", Config.get_db_uri())
    
    # Get bioguides without offices
    print("\n1. Getting bioguides without district offices...")
    bioguides = get_bioguides_without_district_offices(db_uri)
    print(f"   Found {len(bioguides)} members without offices")
    
    if not bioguides:
        print("   No members to process!")
        return 1
    
    # Test with first bioguide
    test_bioguide = bioguides[0]
    print(f"\n2. Testing with bioguide: {test_bioguide}")
    
    # Get contact URL
    contact_url = get_contact_page_url(test_bioguide, db_uri)
    print(f"   Contact URL: {contact_url}")
    
    if not contact_url:
        print("   No contact URL found!")
        # Try another one
        for bg in bioguides[:5]:
            url = get_contact_page_url(bg, db_uri)
            if url:
                print(f"   Found contact URL for {bg}: {url}")
                test_bioguide = bg
                contact_url = url
                break
    
    # Check SQLite database contents
    print("\n3. Checking SQLite database contents...")
    db = SQLiteDatabase(str(Config.get_sqlite_db_path()))
    
    with db.get_session() as session:
        # Check member
        member = session.query(Member).filter_by(bioguideid=test_bioguide).first()
        if member:
            print(f"   Member: {member.name} ({member.state})")
            print(f"   Current: {member.currentmember}")
            print(f"   Website: {member.officialwebsiteurl}")
        
        # Check contact
        contact = session.query(MemberContact).filter_by(bioguideid=test_bioguide).first()
        if contact:
            print(f"   Contact page: {contact.contact_page}")
    
    print("\n4. Ready to run scraping!")
    print(f"   Example command: district-offices --bioguide-id {test_bioguide}")
    
    print("\n" + "=" * 50)
    print("Workflow test completed!")
    return 0

if __name__ == "__main__":
    sys.exit(main())