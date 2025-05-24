#!/usr/bin/env python3
"""
Migration script to convert from PostgreSQL + filesystem storage to SQLite.

This script performs the complete migration of data from the current hybrid system
to a unified SQLite database.
"""

import os
import sys
import sqlite3
import json
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import psycopg2
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from district_offices.config import Config

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SQLiteMigrator:
    """Handles migration from PostgreSQL + filesystem to SQLite."""
    
    def __init__(self, sqlite_db_path: str, postgres_uri: str):
        """Initialize migrator with database paths."""
        self.sqlite_db_path = sqlite_db_path
        self.postgres_uri = postgres_uri
        self.staging_dir = Config.STAGING_DIR
        self.cache_dir = Config.CACHE_ROOT
        self.artifacts_dir = Config.ARTIFACTS_DIR
        
    def create_sqlite_schema(self) -> None:
        """Create SQLite database schema."""
        logger.info("Creating SQLite schema...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            # Core entities
            conn.execute("""
                CREATE TABLE IF NOT EXISTS members (
                    bioguideid TEXT PRIMARY KEY,
                    currentmember BOOLEAN,
                    contact_page TEXT
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS district_offices (
                    office_id TEXT PRIMARY KEY,
                    bioguide_id TEXT,
                    address TEXT,
                    suite TEXT,
                    building TEXT,
                    city TEXT,
                    state TEXT,
                    zip TEXT,
                    phone TEXT,
                    fax TEXT,
                    hours TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bioguide_id) REFERENCES members(bioguideid)
                )
            """)
            
            # Extraction management
            conn.execute("""
                CREATE TABLE IF NOT EXISTS extractions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    bioguide_id TEXT NOT NULL,
                    status TEXT CHECK (status IN ('pending', 'processing', 'validated', 'rejected', 'failed')),
                    extraction_timestamp INTEGER NOT NULL,
                    validation_timestamp INTEGER,
                    source_url TEXT,
                    priority INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bioguide_id) REFERENCES members(bioguideid)
                )
            """)
            
            # Extracted offices (from staging JSON)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS extracted_offices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    extraction_id INTEGER NOT NULL,
                    office_type TEXT,
                    address TEXT,
                    suite TEXT,
                    building TEXT,
                    city TEXT,
                    state TEXT,
                    zip TEXT,
                    phone TEXT,
                    fax TEXT,
                    hours TEXT,
                    office_id_generated TEXT,
                    FOREIGN KEY (extraction_id) REFERENCES extractions(id) ON DELETE CASCADE
                )
            """)
            
            # Artifacts (replaces filesystem storage)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    extraction_id INTEGER NOT NULL,
                    artifact_type TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    content BLOB NOT NULL,
                    content_type TEXT,
                    file_size INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (extraction_id) REFERENCES extractions(id) ON DELETE CASCADE
                )
            """)
            
            # Provenance tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provenance_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    extraction_id INTEGER NOT NULL,
                    process_id TEXT,
                    run_id TEXT,
                    step_name TEXT NOT NULL,
                    step_timestamp INTEGER NOT NULL,
                    step_data TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (extraction_id) REFERENCES extractions(id) ON DELETE CASCADE
                )
            """)
            
            # Cache management
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT UNIQUE NOT NULL,
                    cache_type TEXT NOT NULL,
                    content BLOB NOT NULL,
                    content_type TEXT,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Metadata
            conn.execute("""
                CREATE TABLE IF NOT EXISTS extraction_metadata (
                    extraction_id INTEGER PRIMARY KEY,
                    metadata_json TEXT,
                    FOREIGN KEY (extraction_id) REFERENCES extractions(id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_extractions_bioguide ON extractions(bioguide_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_extractions_status ON extractions(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_extraction ON artifacts(extraction_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_key ON cache_entries(cache_key)")
            
            conn.commit()
            
        logger.info("SQLite schema created successfully")
    
    def migrate_postgresql_data(self) -> None:
        """Migrate data from PostgreSQL to SQLite."""
        logger.info("Migrating PostgreSQL data...")
        
        # Connect to PostgreSQL
        try:
            pg_conn = psycopg2.connect(self.postgres_uri)
        except psycopg2.OperationalError as e:
            logger.error(f"Could not connect to PostgreSQL: {e}")
            logger.info("Skipping PostgreSQL migration")
            return
        
        with sqlite3.connect(self.sqlite_db_path) as sqlite_conn:
            sqlite_conn.execute("PRAGMA foreign_keys = ON")
            
            # Migrate members_contact table if it exists
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("SELECT bioguideid, contact_page FROM members_contact")
                    members_data = cur.fetchall()
                    
                    for bioguideid, contact_page in members_data:
                        sqlite_conn.execute(
                            "INSERT OR REPLACE INTO members (bioguideid, contact_page) VALUES (?, ?)",
                            (bioguideid, contact_page)
                        )
                    
                    logger.info(f"Migrated {len(members_data)} members")
            except psycopg2.Error as e:
                logger.warning(f"Could not migrate members table: {e}")
            
            # Migrate district_offices table if it exists
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                        SELECT office_id, bioguide_id, address, suite, building,
                               city, state, zip, phone, fax, hours
                        FROM district_offices
                    """)
                    offices_data = cur.fetchall()
                    
                    for office_data in offices_data:
                        sqlite_conn.execute("""
                            INSERT OR REPLACE INTO district_offices 
                            (office_id, bioguide_id, address, suite, building,
                             city, state, zip, phone, fax, hours)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, office_data)
                    
                    logger.info(f"Migrated {len(offices_data)} district offices")
            except psycopg2.Error as e:
                logger.warning(f"Could not migrate district_offices table: {e}")
            
            # Migrate extraction_queue table if it exists
            try:
                with pg_conn.cursor() as cur:
                    cur.execute("""
                        SELECT bioguide_id, status, extraction_timestamp, priority,
                               staging_path, error_message
                        FROM extraction_queue
                    """)
                    queue_data = cur.fetchall()
                    
                    for bioguide_id, status, timestamp, priority, staging_path, error_msg in queue_data:
                        sqlite_conn.execute("""
                            INSERT OR REPLACE INTO extractions 
                            (bioguide_id, status, extraction_timestamp, priority, error_message)
                            VALUES (?, ?, ?, ?, ?)
                        """, (bioguide_id, status, timestamp, priority, error_msg))
                    
                    logger.info(f"Migrated {len(queue_data)} extraction queue entries")
            except psycopg2.Error as e:
                logger.warning(f"Could not migrate extraction_queue table: {e}")
            
            sqlite_conn.commit()
        
        pg_conn.close()
        logger.info("PostgreSQL data migration completed")
    
    def migrate_staging_data(self) -> None:
        """Migrate staging directory data to SQLite."""
        logger.info("Migrating staging data...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            
            for status_dir in ['pending', 'validated', 'rejected', 'failed']:
                status_path = self.staging_dir / status_dir
                
                if not status_path.exists():
                    continue
                
                logger.info(f"Processing {status_dir} directory...")
                
                for extraction_dir in status_path.iterdir():
                    if not extraction_dir.is_dir():
                        continue
                    
                    extraction_json_path = extraction_dir / "extraction.json"
                    if not extraction_json_path.exists():
                        logger.warning(f"No extraction.json found in {extraction_dir}")
                        continue
                    
                    try:
                        with open(extraction_json_path, 'r') as f:
                            extraction_data = json.load(f)
                        
                        # Insert extraction record
                        extraction_timestamp = extraction_data.get('extraction_timestamp', 0)
                        validation_timestamp = extraction_data.get('validation_timestamp')
                        
                        cursor = conn.execute("""
                            INSERT INTO extractions 
                            (bioguide_id, status, extraction_timestamp, validation_timestamp, source_url)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            extraction_data['bioguide_id'],
                            status_dir,
                            extraction_timestamp,
                            validation_timestamp,
                            extraction_data.get('source_url')
                        ))
                        
                        extraction_id = cursor.lastrowid
                        
                        # Insert extracted offices
                        for office in extraction_data.get('extracted_offices', []):
                            conn.execute("""
                                INSERT INTO extracted_offices 
                                (extraction_id, office_type, address, suite, building,
                                 city, state, zip, phone, fax, hours, office_id_generated)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                extraction_id,
                                office.get('office_type'),
                                office.get('address'),
                                office.get('suite'),
                                office.get('building'),
                                office.get('city'),
                                office.get('state'),
                                office.get('zip'),
                                office.get('phone'),
                                office.get('fax'),
                                office.get('hours'),
                                office.get('office_id')
                            ))
                        
                        # Insert artifacts
                        artifacts = extraction_data.get('artifacts', {})
                        for artifact_type, artifact_path in artifacts.items():
                            if os.path.exists(artifact_path):
                                with open(artifact_path, 'rb') as f:
                                    content = f.read()
                                
                                conn.execute("""
                                    INSERT INTO artifacts 
                                    (extraction_id, artifact_type, filename, content, file_size)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (
                                    extraction_id,
                                    artifact_type,
                                    os.path.basename(artifact_path),
                                    content,
                                    len(content)
                                ))
                        
                        # Insert provenance log
                        provenance_path = extraction_dir / "provenance.json"
                        if provenance_path.exists():
                            with open(provenance_path, 'r') as f:
                                provenance_data = json.load(f)
                            
                            for step in provenance_data.get('steps', []):
                                conn.execute("""
                                    INSERT INTO provenance_logs 
                                    (extraction_id, process_id, run_id, step_name, 
                                     step_timestamp, step_data)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (
                                    extraction_id,
                                    provenance_data.get('process_id'),
                                    provenance_data.get('run_id'),
                                    step['step_name'],
                                    step['timestamp'],
                                    json.dumps(step.get('data', {}))
                                ))
                        
                        # Insert metadata
                        metadata = extraction_data.get('metadata', {})
                        if metadata:
                            conn.execute("""
                                INSERT INTO extraction_metadata (extraction_id, metadata_json)
                                VALUES (?, ?)
                            """, (extraction_id, json.dumps(metadata)))
                        
                        logger.debug(f"Migrated extraction {extraction_data['bioguide_id']}")
                        
                    except Exception as e:
                        logger.error(f"Error migrating {extraction_dir}: {e}")
                        continue
            
            conn.commit()
        
        logger.info("Staging data migration completed")
    
    def migrate_cache_data(self) -> None:
        """Migrate cache files to SQLite."""
        logger.info("Migrating cache data...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            # Migrate HTML cache
            html_cache_dir = self.cache_dir / "html"
            if html_cache_dir.exists():
                for html_file in html_cache_dir.glob("*.html"):
                    try:
                        with open(html_file, 'rb') as f:
                            content = f.read()
                        
                        cache_key = html_file.stem  # filename without extension
                        
                        conn.execute("""
                            INSERT OR REPLACE INTO cache_entries 
                            (cache_key, cache_type, content, content_type, file_size)
                            VALUES (?, ?, ?, ?, ?)
                        """, (cache_key, 'html', content, 'text/html', len(content)))
                        
                    except Exception as e:
                        logger.error(f"Error migrating cache file {html_file}: {e}")
            
            # Migrate screenshots
            screenshot_dir = self.cache_dir / "screenshots"
            if screenshot_dir.exists():
                for screenshot_file in screenshot_dir.glob("*.png"):
                    try:
                        with open(screenshot_file, 'rb') as f:
                            content = f.read()
                        
                        cache_key = screenshot_file.stem
                        
                        conn.execute("""
                            INSERT OR REPLACE INTO cache_entries 
                            (cache_key, cache_type, content, content_type)
                            VALUES (?, ?, ?, ?)
                        """, (cache_key, 'screenshot', content, 'image/png'))
                        
                    except Exception as e:
                        logger.error(f"Error migrating screenshot {screenshot_file}: {e}")
            
            conn.commit()
        
        logger.info("Cache data migration completed")
    
    def verify_migration(self) -> bool:
        """Verify the migration was successful."""
        logger.info("Verifying migration...")
        
        with sqlite3.connect(self.sqlite_db_path) as conn:
            # Check table counts
            tables = ['members', 'district_offices', 'extractions', 'extracted_offices', 
                     'artifacts', 'provenance_logs', 'cache_entries']
            
            for table in tables:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                logger.info(f"{table}: {count} records")
            
            # Check for foreign key violations
            cursor = conn.execute("PRAGMA foreign_key_check")
            violations = cursor.fetchall()
            
            if violations:
                logger.error(f"Foreign key violations found: {violations}")
                return False
            
            logger.info("Migration verification passed")
            return True
    
    def run_migration(self) -> bool:
        """Run the complete migration process."""
        logger.info("Starting SQLite migration...")
        
        try:
            # Create the SQLite database
            self.create_sqlite_schema()
            
            # Migrate data from various sources
            self.migrate_postgresql_data()
            self.migrate_staging_data()
            self.migrate_cache_data()
            
            # Verify the migration
            if self.verify_migration():
                logger.info("Migration completed successfully!")
                return True
            else:
                logger.error("Migration verification failed!")
                return False
                
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

def main():
    """Main migration function."""
    if len(sys.argv) != 3:
        print("Usage: python migrate_to_sqlite.py <sqlite_db_path> <postgres_uri>")
        print("Example: python migrate_to_sqlite.py /path/to/district_offices.db postgresql://user:pass@localhost/dbname")
        sys.exit(1)
    
    sqlite_db_path = sys.argv[1]
    postgres_uri = sys.argv[2]
    
    # Create backup of existing SQLite file if it exists
    if os.path.exists(sqlite_db_path):
        backup_path = f"{sqlite_db_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(sqlite_db_path, backup_path)
        logger.info(f"Created backup: {backup_path}")
    
    # Run migration
    migrator = SQLiteMigrator(sqlite_db_path, postgres_uri)
    success = migrator.run_migration()
    
    if success:
        logger.info("Migration completed successfully!")
        print(f"SQLite database created at: {sqlite_db_path}")
    else:
        logger.error("Migration failed!")
        sys.exit(1)

if __name__ == "__main__":
    main() 