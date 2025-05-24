#!/usr/bin/env python3
"""Test script for SQLite migration - runs initial sync from PostgreSQL."""

import os
import sys
from pathlib import Path

# Add the src directory to the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from district_offices.storage.sqlite_db import SQLiteDatabase
from district_offices.storage.postgres_sync import PostgreSQLSyncManager
from district_offices.storage.models import Member
from district_offices.config import Config

def main():
    """Run initial sync from PostgreSQL to SQLite."""
    print("Testing SQLite Migration...")
    print("-" * 50)
    
    # Get database URIs
    postgres_uri = os.environ.get("DATABASE_URI", Config.get_db_uri())
    sqlite_path = Config.get_sqlite_db_path()
    
    print(f"PostgreSQL URI: {postgres_uri}")
    print(f"SQLite path: {sqlite_path}")
    print("-" * 50)
    
    # Initialize SQLite database
    print("Initializing SQLite database...")
    db = SQLiteDatabase(str(sqlite_path))
    
    # Initialize sync manager
    print("Initializing PostgreSQL sync manager...")
    sync_manager = PostgreSQLSyncManager(postgres_uri, db)
    
    # Run full sync
    print("\nRunning full sync from PostgreSQL...")
    try:
        stats = sync_manager.full_sync()
        print("\nSync completed successfully!")
        print(f"Results: {stats}")
    except Exception as e:
        print(f"\nSync failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Test querying data
    print("\n" + "-" * 50)
    print("Testing data queries...")
    
    # Get members without offices
    members_without_offices = db.get_members_without_offices()
    print(f"\nMembers without offices: {len(members_without_offices)}")
    if members_without_offices:
        # Need to access within session to avoid detached instance error
        with db.get_session() as session:
            member_ids = session.query(Member.bioguideid).filter(
                Member.currentmember == True
            ).limit(5).all()
            print(f"First 5: {[m[0] for m in member_ids]}")
    
    # Get some extractions
    with db.get_session() as session:
        from district_offices.storage.models import Extraction
        extraction_count = session.query(Extraction).count()
        print(f"\nTotal extractions: {extraction_count}")
    
    # Test backward compatibility
    print("\n" + "-" * 50)
    print("Testing backward compatibility...")
    
    from district_offices import get_bioguides_without_district_offices
    bioguides = get_bioguides_without_district_offices(postgres_uri)
    print(f"Bioguides without offices (via compatibility wrapper): {len(bioguides)}")
    
    print("\n" + "=" * 50)
    print("Migration test completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())