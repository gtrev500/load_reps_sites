#!/usr/bin/env python3
"""
Demonstration of SQLite migration benefits.

This script shows how the new SQLite system simplifies operations
that currently require complex filesystem + database coordination.
"""

import sys
import time
import json
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from district_offices.storage.sqlite_db import SQLiteDatabase

def demo_current_vs_new_approach():
    """Demonstrate the differences between current and new approach."""
    
    print("=== SQLite Migration Demo ===\n")
    
    # Initialize SQLite database
    db = SQLiteDatabase("demo_district_offices.db")
    
    print("1. ADDING A MEMBER (Current: PostgreSQL + filesystem setup)")
    print("   Current: Multiple database connections + directory creation")
    print("   New: Single database call")
    
    # Add a member
    success = db.add_member("D000230", "https://dondavis.house.gov/contact")
    print(f"   Result: {'Success' if success else 'Failed'}")
    
    print("\n2. STORING EXTRACTION DATA (Current: JSON files + directories)")
    print("   Current: Create staging directory + multiple file writes")
    print("   New: Single transaction with all data")
    
    # Create extraction with all data
    extraction_data = {
        'bioguide_id': 'D000230',
        'source_url': 'https://dondavis.house.gov/contact',
        'extracted_offices': [
            {
                'office_type': 'District Office',
                'address': '306 E Colonial Ave',
                'city': 'Elizabeth City',
                'state': 'NC',
                'zip': '27909',
                'phone': '(252) 999-7600'
            }
        ],
        'artifacts': {
            'html': b'<html><body>Sample HTML content</body></html>',
            'contact_sections': b'<div>Contact section HTML</div>'
        },
        'provenance_steps': [
            {
                'step_name': 'html_extracted',
                'timestamp': int(time.time()),
                'data': {'cache_path': '/cache/html/sample.html'}
            },
            {
                'step_name': 'llm_extraction_complete', 
                'timestamp': int(time.time()),
                'data': {'offices_count': 1}
            }
        ],
        'metadata': {'offices_count': 1}
    }
    
    extraction_id = db.create_extraction(**extraction_data)
    print(f"   Result: Created extraction ID {extraction_id}")
    
    print("\n3. QUERYING DATA (Current: File system traversal + database queries)")
    print("   Current: Scan directories + multiple database calls")
    print("   New: Single SQL query")
    
    # Get pending extractions
    pending = db.get_pending_extractions(limit=5)
    print(f"   Found {len(pending)} pending extractions")
    
    print("\n4. CACHING (Current: Filesystem with manual cache management)")
    print("   Current: File I/O + manual expiration checking")
    print("   New: Database with automatic expiration")
    
    # Store and retrieve cached content
    cache_key = "sample_page"
    sample_html = b"<html><body>Cached page content</body></html>"
    
    db.store_cached_content(cache_key, "html", sample_html, "text/html")
    cached_content = db.get_cached_content(cache_key, "html")
    print(f"   Cached content retrieved: {len(cached_content)} bytes")
    
    print("\n5. VALIDATION WORKFLOW (Current: Move files between directories)")
    print("   Current: File moves + JSON updates + database updates")
    print("   New: Single status update")
    
    # Update extraction status
    if extraction_id:
        success = db.update_extraction_status(extraction_id, 'validated')
        print(f"   Validation result: {'Success' if success else 'Failed'}")
    
    print("\n6. GETTING STATISTICS (Current: Directory scanning + database queries)")
    print("   Current: Recursive file counting + multiple SQL queries")
    print("   New: Single database query")
    
    stats = db.get_database_stats()
    print("   Database Statistics:")
    for key, value in stats.items():
        if isinstance(value, dict):
            print(f"     {key}: {value}")
        else:
            print(f"     {key}: {value}")
    
    print("\n7. BACKUP & DEPLOYMENT (Current: PostgreSQL + directories)")
    print("   Current: Database backup + tar/zip of filesystem")
    print("   New: Single SQLite file copy")
    print(f"   Database file: demo_district_offices.db")
    
    print("\n=== Migration Benefits Summary ===")
    print("✅ Simplified deployment (single file)")
    print("✅ ACID compliance for all operations")
    print("✅ Unified querying across all data")
    print("✅ Automatic cache management")
    print("✅ Better data integrity with foreign keys")
    print("✅ Easier backup and restore")
    print("✅ Reduced I/O operations")
    print("✅ Better error handling and rollback")

def demo_migration_process():
    """Show what the migration process would look like."""
    
    print("\n=== Migration Process Demo ===")
    print("1. Create SQLite schema ✓")
    print("2. Migrate PostgreSQL data ✓")
    print("3. Migrate staging filesystem data ✓")
    print("4. Migrate cache files ✓")
    print("5. Verify data integrity ✓")
    print("6. Update application code ✓")
    print("7. Deploy new system ✓")
    
    print("\nMigration command example:")
    print("python scripts/migrate_to_sqlite.py ./data/district_offices.db postgresql://user:pass@localhost/gov")

def main():
    """Run the demonstration."""
    try:
        demo_current_vs_new_approach()
        demo_migration_process()
        
        print("\n=== Next Steps ===")
        print("1. Review the migration plan in SQLITE_MIGRATION_PLAN.md")
        print("2. Test the migration script with a copy of your data")
        print("3. Update your application code to use SQLiteDatabase")
        print("4. Run comprehensive tests")
        print("5. Deploy to production")
        
    except Exception as e:
        print(f"Demo failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean up demo database
        demo_db_path = Path("demo_district_offices.db")
        if demo_db_path.exists():
            demo_db_path.unlink()
            print(f"\nCleaned up demo database: {demo_db_path}")

if __name__ == "__main__":
    main() 