#!/usr/bin/env python3
"""
Design for PostgreSQL <-> SQLite sync operations - SYNCHRONOUS VERSION
Demonstrates the integration points between upstream and local processing
"""

import sqlite3
import psycopg2
from typing import List, Dict, Optional
from datetime import datetime
import logging
from contextlib import contextmanager

log = logging.getLogger(__name__)


class PostgreSQLSyncManager:
    """Manages sync operations between PostgreSQL and SQLite (synchronous)"""
    
    def __init__(self, sqlite_path: str, postgres_uri: str):
        self.sqlite_path = sqlite_path
        self.postgres_uri = postgres_uri
        
    @contextmanager
    def _get_sqlite_connection(self):
        """Get SQLite connection with proper settings"""
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()
            
    def sync_from_upstream(self) -> Dict[str, int]:
        """Import members and contact URLs from PostgreSQL to SQLite"""
        stats = {"members": 0, "contacts": 0}
        
        # Connect to PostgreSQL
        pg_conn = psycopg2.connect(self.postgres_uri)
        
        try:
            with pg_conn.cursor() as pg_cur:
                # 1. Sync members table
                pg_cur.execute("""
                    SELECT bioguideid, currentmember, officialwebsiteurl,
                           firstname || ' ' || lastname as name, state
                    FROM members 
                    WHERE currentmember = true
                """)
                members = pg_cur.fetchall()
                
                with self._get_sqlite_connection() as sqlite_conn:
                    sqlite_conn.execute("DELETE FROM members")  # Clear old data
                    sqlite_conn.executemany(
                        """INSERT INTO members (bioguideid, currentmember, 
                           officialwebsiteurl, name, state) 
                           VALUES (?, ?, ?, ?, ?)""",
                        members
                    )
                    stats["members"] = len(members)
                    
                    # 2. Sync members_contact table
                    pg_cur.execute("""
                        SELECT bioguideid, contact_page 
                        FROM members_contact
                    """)
                    contacts = pg_cur.fetchall()
                    
                    sqlite_conn.execute("DELETE FROM members_contact")
                    sqlite_conn.executemany(
                        """INSERT INTO members_contact (bioguideid, contact_page) 
                           VALUES (?, ?)""",
                        contacts
                    )
                    stats["contacts"] = len(contacts)
                    
                    # 3. Log sync operation
                    sqlite_conn.execute("""
                        INSERT INTO sync_log (sync_type, sync_direction, 
                                            records_processed, status)
                        VALUES ('full_import', 'from_upstream', ?, 'completed')
                    """, (stats["members"] + stats["contacts"],))
                    
                    sqlite_conn.commit()
                
        finally:
            pg_conn.close()
            
        log.info(f"Synced {stats['members']} members and {stats['contacts']} contacts")
        return stats
    
    def export_validated_offices(self, batch_size: int = 100) -> int:
        """Export validated offices from SQLite to PostgreSQL"""
        exported = 0
        
        with self._get_sqlite_connection() as sqlite_conn:
            # Get unsynced validated offices
            cursor = sqlite_conn.execute("""
                SELECT * FROM validated_offices 
                WHERE synced_to_upstream = 0
                ORDER BY validated_at
            """)
            
            offices = cursor.fetchall()
            
            if not offices:
                log.info("No validated offices to export")
                return 0
            
            # Connect to PostgreSQL
            pg_conn = psycopg2.connect(self.postgres_uri)
            
            try:
                # Batch export to PostgreSQL
                for i in range(0, len(offices), batch_size):
                    batch = offices[i:i + batch_size]
                    
                with pg_conn.cursor() as pg_cur:
                    for office in batch:
                        # SQLite Row objects can be accessed like dicts
                        pg_cur.execute("""
                            INSERT INTO district_offices 
                            (office_id, bioguide_id, address, suite, building,
                             city, state, zip, phone, fax, hours)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (office_id) DO UPDATE SET
                                address = EXCLUDED.address,
                                suite = EXCLUDED.suite,
                                building = EXCLUDED.building,
                                city = EXCLUDED.city,
                                state = EXCLUDED.state,
                                zip = EXCLUDED.zip,
                                phone = EXCLUDED.phone,
                                fax = EXCLUDED.fax,
                                hours = EXCLUDED.hours
                        """, (
                            office['office_id'],
                            office['bioguide_id'],
                            office['address'],
                            office['suite'],
                            office['building'],
                            office['city'],
                            office['state'],
                            office['zip'],
                            office['phone'],
                            office['fax'],
                            office['hours']
                        ))
                    
                    pg_conn.commit()
                    
                    # Get office IDs for marking as synced
                    office_ids = [office['office_id'] for office in batch]
                    
                    # Mark as synced in SQLite
                    placeholders = ','.join('?' * len(office_ids))
                    sqlite_conn.execute(f"""
                        UPDATE validated_offices 
                        SET synced_to_upstream = 1, synced_at = CURRENT_TIMESTAMP
                        WHERE office_id IN ({placeholders})
                    """, office_ids)
                    
                    exported += len(batch)
                    log.info(f"Exported batch of {len(batch)} offices")
                
                # Log export operation
                sqlite_conn.execute("""
                    INSERT INTO sync_log (sync_type, sync_direction, 
                                        records_processed, status)
                    VALUES ('offices_export', 'to_upstream', ?, 'completed')
                """, (exported,))
                
                sqlite_conn.commit()
                
            finally:
                pg_conn.close()
        
        log.info(f"Successfully exported {exported} validated offices to PostgreSQL")
        return exported
    
    def get_sync_status(self) -> Dict:
        """Get current sync status and statistics"""
        with self._get_sqlite_connection() as conn:
            # Get last sync times
            cursor = conn.execute("""
                SELECT sync_type, MAX(completed_at) as last_sync
                FROM sync_log
                WHERE status = 'completed'
                GROUP BY sync_type
            """)
            last_syncs = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Get pending exports
            cursor = conn.execute("""
                SELECT COUNT(*) FROM validated_offices 
                WHERE synced_to_upstream = 0
            """)
            pending_exports = cursor.fetchone()[0]
            
            # Get total processed
            cursor = conn.execute("""
                SELECT COUNT(*) FROM extractions
                WHERE status = 'validated'
            """)
            total_validated = cursor.fetchone()[0]
            
            return {
                "last_import": last_syncs.get("full_import"),
                "last_export": last_syncs.get("offices_export"),
                "pending_exports": pending_exports,
                "total_validated": total_validated
            }


# CLI Commands for sync operations
def sync_command(args):
    """CLI command to sync data from PostgreSQL"""
    sync_mgr = PostgreSQLSyncManager(args.sqlite_path, args.postgres_uri)
    
    if args.import_data:
        print("Importing data from PostgreSQL...")
        stats = sync_mgr.sync_from_upstream()
        print(f"Imported {stats['members']} members and {stats['contacts']} contacts")
    
    if args.export_data:
        print("Exporting validated offices to PostgreSQL...")
        count = sync_mgr.export_validated_offices()
        print(f"Exported {count} offices")
    
    if args.status:
        status = sync_mgr.get_sync_status()
        print("\nSync Status:")
        print(f"  Last import: {status['last_import'] or 'Never'}")
        print(f"  Last export: {status['last_export'] or 'Never'}")
        print(f"  Pending exports: {status['pending_exports']}")
        print(f"  Total validated: {status['total_validated']}")


if __name__ == "__main__":
    # Example usage
    import argparse
    
    parser = argparse.ArgumentParser(description="PostgreSQL sync operations")
    parser.add_argument("--sqlite-path", required=True, help="Path to SQLite database")
    parser.add_argument("--postgres-uri", required=True, help="PostgreSQL connection URI")
    parser.add_argument("--import-data", action="store_true", help="Import from PostgreSQL")
    parser.add_argument("--export-data", action="store_true", help="Export to PostgreSQL")
    parser.add_argument("--status", action="store_true", help="Show sync status")
    
    args = parser.parse_args()
    sync_command(args)