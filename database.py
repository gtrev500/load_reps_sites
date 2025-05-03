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