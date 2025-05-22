#!/usr/bin/env python3

import logging
import os
import sys
import psycopg2
from typing import List, Dict, Tuple, Optional, Any

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
log = logging.getLogger(__name__)

def get_db_connection(database_uri: str):
    """Establishes a connection to the PostgreSQL database.
    
    Args:
        database_uri: URI string for connecting to the database
        
    Returns:
        A database connection object
    """
    try:
        conn = psycopg2.connect(database_uri)
        return conn
    except psycopg2.OperationalError as e:
        log.error(f"Database connection failed: {e}")
        sys.exit(1)
    except Exception as e:
        log.error(f"An unexpected error occurred during DB connection: {e}")
        sys.exit(1)

def check_district_office_exists(bioguide_id: str, database_uri: str) -> bool:
    """Check if district office information exists for a given bioguide ID.
    
    Args:
        bioguide_id: The bioguide ID to check
        database_uri: URI string for connecting to the database
        
    Returns:
        True if district office info exists, False otherwise
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM district_offices WHERE bioguide_id = %s", 
                (bioguide_id,)
            )
            result = cur.fetchone()
            return result[0] > 0
    except psycopg2.Error as e:
        log.error(f"Database error checking district office: {e}")
        return False
    finally:
        if conn:
            conn.close()
            
def get_contact_page_url(bioguide_id: str, database_uri: str) -> Optional[str]:
    """Get the contact page URL for a given bioguide ID from members_contact table.
    
    Args:
        bioguide_id: The bioguide ID to look up
        database_uri: URI string for connecting to the database
        
    Returns:
        Contact page URL if found, None otherwise
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT contact_page FROM members_contact WHERE bioguideid = %s", 
                (bioguide_id,)
            )
            result = cur.fetchone()
            return result[0] if result else None
    except psycopg2.Error as e:
        log.error(f"Database error retrieving contact page URL: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_bioguides_without_district_offices(database_uri: str) -> List[str]:
    """Get list of bioguide IDs that exist in members_contact but not in district_offices.
    
    Args:
        database_uri: URI string for connecting to the database
        
    Returns:
        List of bioguide IDs without district office information
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            # Get bioguide IDs from members_contact that don't exist in district_offices
            cur.execute("""
                SELECT DISTINCT mc.bioguideid
                FROM members_contact mc
                LEFT JOIN district_offices d_off ON mc.bioguideid = d_off.bioguide_id
                WHERE d_off.bioguide_id IS NULL
                AND EXISTS (SELECT 1 FROM members m WHERE m.bioguideid = mc.bioguideid AND m.currentmember = true)
            """)
            results = cur.fetchall()
            return [row[0] for row in results]
    except psycopg2.Error as e:
        log.error(f"Database error retrieving bioguides without district offices: {e}")
        return []
    finally:
        if conn:
            conn.close()


def store_district_office(office_data: Dict[str, Any], database_uri: str) -> bool:
    """Store district office information in the database.
    
    Args:
        office_data: Dictionary containing district office information
        database_uri: URI string for connecting to the database
        
    Returns:
        True if storing was successful, False otherwise
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            # Generate a unique office_id (bioguide_id-city)
            city = office_data.get('city', 'unknown').lower().replace(' ', '_')
            office_id = f"{office_data['bioguide_id']}-{city}"
            
            # Insert the district office data
            insert_sql = """
                INSERT INTO district_offices (
                    office_id, bioguide_id, address, suite, building,
                    city, state, zip, phone, fax, hours
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (office_id) DO UPDATE SET
                    address = EXCLUDED.address,
                    suite = EXCLUDED.suite,
                    building = EXCLUDED.building,
                    city = EXCLUDED.city,
                    state = EXCLUDED.state,
                    zip = EXCLUDED.zip,
                    phone = EXCLUDED.phone,
                    fax = EXCLUDED.fax,
                    hours = EXCLUDED.hours;
            """
            
            cur.execute(insert_sql, (
                office_id,
                office_data['bioguide_id'],
                office_data.get('address'),
                office_data.get('suite'),
                office_data.get('building'),
                office_data.get('city'),
                office_data.get('state'),
                office_data.get('zip'),
                office_data.get('phone'),
                office_data.get('fax'),
                office_data.get('hours')
            ))
            
            conn.commit()
            log.info(f"Successfully stored district office for {office_data['bioguide_id']} in {city}")
            return True
    except psycopg2.Error as e:
        log.error(f"Database error storing district office: {e}")
        conn.rollback()
        return False
    except Exception as e:
        log.error(f"Unexpected error storing district office: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

# --- Extraction Queue Functions ---

def create_extraction_queue_table(database_uri: str) -> bool:
    """Create the extraction_queue table if it doesn't exist.
    
    Args:
        database_uri: URI string for connecting to the database
        
    Returns:
        True if successful, False otherwise
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            create_sql = """
                CREATE TABLE IF NOT EXISTS extraction_queue (
                    bioguide_id VARCHAR PRIMARY KEY,
                    status VARCHAR CHECK (status IN ('pending', 'processing', 'staged', 'validated', 'failed')),
                    extraction_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    validation_timestamp TIMESTAMP,
                    staging_path VARCHAR,
                    priority INTEGER DEFAULT 0,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE INDEX IF NOT EXISTS idx_extraction_queue_status ON extraction_queue(status);
                CREATE INDEX IF NOT EXISTS idx_extraction_queue_priority ON extraction_queue(priority DESC);
            """
            cur.execute(create_sql)
            conn.commit()
            log.info("Extraction queue table created successfully")
            return True
    except psycopg2.Error as e:
        log.error(f"Database error creating extraction queue table: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def queue_bioguide_for_extraction(
    bioguide_id: str, 
    database_uri: str, 
    priority: int = 0
) -> bool:
    """Queue a bioguide ID for extraction.
    
    Args:
        bioguide_id: The bioguide ID to queue
        database_uri: URI string for connecting to the database
        priority: Priority level (higher = more priority)
        
    Returns:
        True if successful, False otherwise
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            insert_sql = """
                INSERT INTO extraction_queue (bioguide_id, status, priority)
                VALUES (%s, 'pending', %s)
                ON CONFLICT (bioguide_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    priority = EXCLUDED.priority,
                    updated_at = CURRENT_TIMESTAMP
            """
            cur.execute(insert_sql, (bioguide_id, priority))
            conn.commit()
            log.info(f"Queued {bioguide_id} for extraction with priority {priority}")
            return True
    except psycopg2.Error as e:
        log.error(f"Database error queueing bioguide for extraction: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_queued_bioguides(
    database_uri: str, 
    status: str = 'pending', 
    limit: Optional[int] = None
) -> List[str]:
    """Get queued bioguide IDs by status.
    
    Args:
        database_uri: URI string for connecting to the database
        status: Status to filter by
        limit: Maximum number of results to return
        
    Returns:
        List of bioguide IDs
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            sql = """
                SELECT bioguide_id 
                FROM extraction_queue 
                WHERE status = %s 
                ORDER BY priority DESC, created_at ASC
            """
            params = [status]
            
            if limit:
                sql += " LIMIT %s"
                params.append(limit)
            
            cur.execute(sql, params)
            results = cur.fetchall()
            return [row[0] for row in results]
    except psycopg2.Error as e:
        log.error(f"Database error retrieving queued bioguides: {e}")
        return []
    finally:
        if conn:
            conn.close()

def update_extraction_status(
    bioguide_id: str,
    database_uri: str,
    status: str,
    staging_path: Optional[str] = None,
    error_message: Optional[str] = None
) -> bool:
    """Update the status of an extraction.
    
    Args:
        bioguide_id: The bioguide ID
        database_uri: URI string for connecting to the database
        status: New status
        staging_path: Optional staging path
        error_message: Optional error message
        
    Returns:
        True if successful, False otherwise
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            update_sql = """
                UPDATE extraction_queue 
                SET status = %s, staging_path = %s, error_message = %s, updated_at = CURRENT_TIMESTAMP
            """
            params = [status, staging_path, error_message]
            
            if status == 'validated':
                update_sql += ", validation_timestamp = CURRENT_TIMESTAMP"
            
            update_sql += " WHERE bioguide_id = %s"
            params.append(bioguide_id)
            
            cur.execute(update_sql, params)
            conn.commit()
            
            if cur.rowcount > 0:
                log.info(f"Updated extraction status for {bioguide_id} to {status}")
                return True
            else:
                log.warning(f"No rows updated for {bioguide_id}")
                return False
                
    except psycopg2.Error as e:
        log.error(f"Database error updating extraction status: {e}")
        conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def get_extraction_queue_summary(database_uri: str) -> Dict[str, Any]:
    """Get a summary of the extraction queue.
    
    Args:
        database_uri: URI string for connecting to the database
        
    Returns:
        Dictionary with queue statistics
    """
    conn = get_db_connection(database_uri)
    try:
        with conn.cursor() as cur:
            # Get status counts
            cur.execute("""
                SELECT status, COUNT(*) 
                FROM extraction_queue 
                GROUP BY status
            """)
            status_counts = dict(cur.fetchall())
            
            # Get total count
            cur.execute("SELECT COUNT(*) FROM extraction_queue")
            total_count = cur.fetchone()[0]
            
            # Get oldest pending item
            cur.execute("""
                SELECT MIN(created_at) 
                FROM extraction_queue 
                WHERE status = 'pending'
            """)
            oldest_pending = cur.fetchone()[0]
            
            return {
                "total_items": total_count,
                "status_counts": status_counts,
                "oldest_pending": oldest_pending.isoformat() if oldest_pending else None
            }
            
    except psycopg2.Error as e:
        log.error(f"Database error getting extraction queue summary: {e}")
        return {}
    finally:
        if conn:
            conn.close()