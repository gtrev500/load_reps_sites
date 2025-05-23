#!/usr/bin/env python3
"""Async database operations using asyncpg."""

import logging
import sys
from typing import List, Dict, Optional, Any
import asyncpg
from asyncpg import Pool

log = logging.getLogger(__name__)

# Global connection pool
_connection_pool: Optional[Pool] = None


async def get_connection_pool(database_uri: str, min_size: int = 10, max_size: int = 20) -> Pool:
    """Get or create the global connection pool.
    
    Args:
        database_uri: PostgreSQL connection URI
        min_size: Minimum number of connections in pool
        max_size: Maximum number of connections in pool
        
    Returns:
        Connection pool instance
    """
    global _connection_pool
    
    if _connection_pool is None:
        try:
            _connection_pool = await asyncpg.create_pool(
                database_uri,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60
            )
            log.info(f"Created connection pool with {min_size}-{max_size} connections")
        except Exception as e:
            log.error(f"Failed to create connection pool: {e}")
            raise
    
    return _connection_pool


async def close_connection_pool():
    """Close the global connection pool."""
    global _connection_pool
    
    if _connection_pool:
        await _connection_pool.close()
        _connection_pool = None
        log.info("Closed connection pool")


async def check_district_office_exists(bioguide_id: str, database_uri: str) -> bool:
    """Check if district office information already exists for a bioguide ID.
    
    Args:
        bioguide_id: The bioguide ID to check
        database_uri: URI for the database connection
        
    Returns:
        True if district office data exists, False otherwise
    """
    pool = await get_connection_pool(database_uri)
    
    query = """
        SELECT COUNT(*) FROM district_offices 
        WHERE bioguide_id = $1
    """
    
    try:
        async with pool.acquire() as conn:
            count = await conn.fetchval(query, bioguide_id)
            return count > 0
    except Exception as e:
        log.error(f"Error checking district office existence: {e}")
        return False


async def get_contact_page_url(bioguide_id: str, database_uri: str) -> Optional[str]:
    """Get the contact page URL for a given bioguide ID.
    
    Args:
        bioguide_id: The bioguide ID to look up
        database_uri: URI for the database connection
        
    Returns:
        The contact page URL if found, None otherwise
    """
    pool = await get_connection_pool(database_uri)
    
    query = """
        SELECT contact_page FROM members_contact 
        WHERE bioguideid = $1
    """
    
    try:
        async with pool.acquire() as conn:
            result = await conn.fetchval(query, bioguide_id)
            return result
    except Exception as e:
        log.error(f"Error fetching contact page URL: {e}")
        return None


async def get_bioguides_without_district_offices(database_uri: str) -> List[str]:
    """Get all bioguide IDs that don't have district office information.
    
    Args:
        database_uri: URI for the database connection
        
    Returns:
        List of bioguide IDs without district office data
    """
    pool = await get_connection_pool(database_uri)
    
    query = """
        SELECT DISTINCT mc.bioguideid 
        FROM members_contact mc
        LEFT JOIN district_offices d ON mc.bioguideid = d.bioguide_id
        WHERE d.bioguide_id IS NULL 
        AND mc.contact_page IS NOT NULL
        ORDER BY mc.bioguideid
    """
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [row['bioguideid'] for row in rows]
    except Exception as e:
        log.error(f"Error fetching bioguides without district offices: {e}")
        return []


async def store_district_office(office_data: Dict[str, Any], database_uri: str) -> bool:
    """Store district office information in the database.
    
    Args:
        office_data: Dictionary containing office information
        database_uri: URI for the database connection
        
    Returns:
        True if successful, False otherwise
    """
    pool = await get_connection_pool(database_uri)
    
    # Required fields
    required_fields = ['bioguide_id', 'office_id', 'office_type']
    for field in required_fields:
        if field not in office_data:
            log.error(f"Missing required field: {field}")
            return False
    
    # Build the insert query
    fields = list(office_data.keys())
    placeholders = [f'${i+1}' for i in range(len(fields))]
    values = [office_data[field] for field in fields]
    
    query = f"""
        INSERT INTO district_offices ({', '.join(fields)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT (office_id) DO UPDATE SET
        {', '.join([f"{field} = EXCLUDED.{field}" for field in fields if field != 'office_id'])}
    """
    
    try:
        async with pool.acquire() as conn:
            await conn.execute(query, *values)
            log.info(f"Stored district office: {office_data['office_id']}")
            return True
    except Exception as e:
        log.error(f"Error storing district office: {e}")
        log.error(f"Query: {query}")
        log.error(f"Values: {values}")
        return False


# Extraction queue functions (async versions)

async def create_extraction_queue_table(database_uri: str) -> bool:
    """Create the extraction queue table if it doesn't exist.
    
    Args:
        database_uri: URI for the database connection
        
    Returns:
        True if successful, False otherwise
    """
    pool = await get_connection_pool(database_uri)
    
    query = """
        CREATE TABLE IF NOT EXISTS extraction_queue (
            bioguide_id VARCHAR(20) PRIMARY KEY,
            status VARCHAR(20) DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            attempts INTEGER DEFAULT 0,
            last_error TEXT,
            extracted_data JSONB
        )
    """
    
    try:
        async with pool.acquire() as conn:
            await conn.execute(query)
            log.info("Extraction queue table ready")
            return True
    except Exception as e:
        log.error(f"Error creating extraction queue table: {e}")
        return False


async def queue_bioguide_for_extraction(
    bioguide_id: str, 
    database_uri: str,
    priority: int = 0
) -> bool:
    """Add a bioguide ID to the extraction queue.
    
    Args:
        bioguide_id: The bioguide ID to queue
        database_uri: URI for the database connection
        priority: Priority level (higher = more important)
        
    Returns:
        True if successful, False otherwise
    """
    pool = await get_connection_pool(database_uri)
    
    query = """
        INSERT INTO extraction_queue (bioguide_id, priority)
        VALUES ($1, $2)
        ON CONFLICT (bioguide_id) DO UPDATE
        SET priority = GREATEST(extraction_queue.priority, $2),
            updated_at = CURRENT_TIMESTAMP
    """
    
    try:
        async with pool.acquire() as conn:
            await conn.execute(query, bioguide_id, priority)
            log.info(f"Queued {bioguide_id} with priority {priority}")
            return True
    except Exception as e:
        log.error(f"Error queuing bioguide: {e}")
        return False


async def get_queued_bioguides(
    database_uri: str,
    status: str = 'pending',
    limit: int = 100
) -> List[Dict[str, Any]]:
    """Get bioguide IDs from the extraction queue.
    
    Args:
        database_uri: URI for the database connection
        status: Status filter (pending, processing, completed, failed)
        limit: Maximum number of records to return
        
    Returns:
        List of queue entries
    """
    pool = await get_connection_pool(database_uri)
    
    query = """
        SELECT bioguide_id, status, priority, attempts, last_error
        FROM extraction_queue
        WHERE status = $1
        ORDER BY priority DESC, created_at ASC
        LIMIT $2
    """
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, status, limit)
            return [dict(row) for row in rows]
    except Exception as e:
        log.error(f"Error fetching queued bioguides: {e}")
        return []


async def update_extraction_status(
    bioguide_id: str,
    database_uri: str,
    status: str,
    error_message: Optional[str] = None,
    extracted_data: Optional[Dict[str, Any]] = None
) -> bool:
    """Update the status of a bioguide in the extraction queue.
    
    Args:
        bioguide_id: The bioguide ID to update
        database_uri: URI for the database connection
        status: New status
        error_message: Error message if failed
        extracted_data: Extracted data to store
        
    Returns:
        True if successful, False otherwise
    """
    pool = await get_connection_pool(database_uri)
    
    query = """
        UPDATE extraction_queue
        SET status = $2,
            updated_at = CURRENT_TIMESTAMP,
            attempts = attempts + 1,
            last_error = $3,
            extracted_data = $4
        WHERE bioguide_id = $1
    """
    
    try:
        async with pool.acquire() as conn:
            # Convert extracted_data to JSON if provided
            import json
            json_data = json.dumps(extracted_data) if extracted_data else None
            
            await conn.execute(query, bioguide_id, status, error_message, json_data)
            log.info(f"Updated {bioguide_id} status to {status}")
            return True
    except Exception as e:
        log.error(f"Error updating extraction status: {e}")
        return False


async def get_extraction_queue_summary(database_uri: str) -> Dict[str, Any]:
    """Get a summary of the extraction queue status.
    
    Args:
        database_uri: URI for the database connection
        
    Returns:
        Dictionary with queue statistics
    """
    pool = await get_connection_pool(database_uri)
    
    query = """
        SELECT 
            status,
            COUNT(*) as count,
            AVG(attempts) as avg_attempts
        FROM extraction_queue
        GROUP BY status
    """
    
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            
            summary = {
                'total': 0,
                'by_status': {}
            }
            
            for row in rows:
                status = row['status']
                count = row['count']
                summary['total'] += count
                summary['by_status'][status] = {
                    'count': count,
                    'avg_attempts': float(row['avg_attempts'])
                }
            
            return summary
    except Exception as e:
        log.error(f"Error getting queue summary: {e}")
        return {'total': 0, 'by_status': {}}