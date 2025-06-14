#!/usr/bin/env python3
"""
SQLite database management using SQLAlchemy ORM.
Handles all local processing and staging operations.
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import time

from sqlalchemy import create_engine, and_, or_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import SQLAlchemyError

from .models import (
    SQLiteBase, Member, MemberContact, Extraction, ExtractedOffice,
    ValidatedOffice, Artifact, ProvenanceLog, CacheEntry, SyncLog,
    ExtractionMetadata
)

log = logging.getLogger(__name__)


class SQLiteDatabase:
    """Manages the local SQLite database for district office processing."""
    
    def __init__(self, db_path: str, echo: bool = False):
        """Initialize SQLite database connection.
        
        Args:
            db_path: Path to SQLite database file
            echo: Whether to echo SQL statements (for debugging)
        """
        self.db_path = db_path
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            echo=echo,
            connect_args={
                'check_same_thread': False,  # Allow multi-threaded access
                'timeout': 30.0  # 30 second timeout for locks
            }
        )
        
        # Create session factory
        self.Session = sessionmaker(bind=self.engine)
        
        # Initialize database
        self._init_database()
    
    def _init_database(self):
        """Initialize database with all tables and settings."""
        # Create all tables
        SQLiteBase.metadata.create_all(self.engine)
        
        # Set pragmas for better performance
        from sqlalchemy import text
        with self.engine.connect() as conn:
            conn.execute(text("PRAGMA foreign_keys = ON"))
            conn.execute(text("PRAGMA journal_mode = WAL"))
            conn.execute(text("PRAGMA synchronous = NORMAL"))
            conn.execute(text("PRAGMA temp_store = MEMORY"))
            conn.execute(text("PRAGMA mmap_size = 30000000000"))
            conn.commit()
    
    @contextmanager
    def get_session(self) -> Session:
        """Get a database session with automatic cleanup.
        
        Yields:
            Session: SQLAlchemy session
        """
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    # ========================================================================
    # Member Management
    # ========================================================================
    
    def upsert_member(self, member_data: Dict[str, Any]) -> Member:
        """Insert or update a member.
        
        Args:
            member_data: Dictionary with member information
            
        Returns:
            Member: The created or updated member
        """
        with self.get_session() as session:
            member = session.query(Member).filter_by(
                bioguideid=member_data['bioguideid']
            ).first()
            
            if member:
                # Update existing
                for key, value in member_data.items():
                    setattr(member, key, value)
            else:
                # Create new
                member = Member(**member_data)
                session.add(member)
            
            session.commit()
            return member
    
    def get_members_without_offices(self) -> List[Member]:
        """Get members who don't have validated district offices.
        
        Returns:
            List[Member]: Members without offices
        """
        with self.get_session() as session:
            return session.query(Member).filter(
                and_(
                    Member.currentmember == True,
                    ~Member.validated_offices.any()
                )
            ).all()
    
    def get_member_contact(self, bioguide_id: str) -> Optional[MemberContact]:
        """Get contact information for a member.
        
        Args:
            bioguide_id: Member's bioguide ID
            
        Returns:
            MemberContact: Contact information or None
        """
        with self.get_session() as session:
            return session.query(MemberContact).filter_by(
                bioguideid=bioguide_id
            ).first()
    
    # ========================================================================
    # Extraction Management
    # ========================================================================
    
    def create_extraction(self, bioguide_id: str, source_url: str, 
                         priority: int = 0) -> int:
        """Create a new extraction record.
        
        Args:
            bioguide_id: Member's bioguide ID
            source_url: URL being scraped
            priority: Extraction priority
            
        Returns:
            int: Created extraction ID
        """
        with self.get_session() as session:
            # Check if member exists
            member = session.query(Member).filter_by(bioguideid=bioguide_id).first()
            if not member:
                raise ValueError(f"Bioguide ID '{bioguide_id}' not found in members table. "
                               f"Please ensure this is a valid current member ID.")
            
            extraction = Extraction(
                bioguide_id=bioguide_id,
                source_url=source_url,
                priority=priority,
                extraction_timestamp=int(time.time()),
                status='pending'
            )
            session.add(extraction)
            session.commit()
            # Return the ID while still in session
            return extraction.id
    
    def get_pending_extractions(self, limit: int = 10) -> List[Extraction]:
        """Get pending extractions ordered by priority.
        
        Args:
            limit: Maximum number to return
            
        Returns:
            List[Extraction]: Pending extractions
        """
        with self.get_session() as session:
            return session.query(Extraction).filter(
                Extraction.status == 'pending'
            ).order_by(
                Extraction.priority.desc(),
                Extraction.created_at
            ).limit(limit).all()
    
    def get_extraction_by_bioguide(self, bioguide_id: str) -> Optional[Extraction]:
        """Get the most recent extraction for a bioguide ID.
        
        Args:
            bioguide_id: Bioguide ID
            
        Returns:
            Optional[Extraction]: Most recent extraction or None
        """
        with self.get_session() as session:
            return session.query(Extraction).filter(
                Extraction.bioguide_id == bioguide_id
            ).order_by(
                Extraction.created_at.desc()
            ).first()
    
    def get_extractions_by_status(self, status: str) -> List[Extraction]:
        """Get all extractions with a specific status.
        
        Args:
            status: Status to filter by
            
        Returns:
            List[Extraction]: Extractions with the given status
        """
        with self.get_session() as session:
            return session.query(Extraction).filter(
                Extraction.status == status
            ).order_by(
                Extraction.created_at
            ).all()
    
    # Alias for compatibility
    get_latest_extraction = get_extraction_by_bioguide
    
    def update_extraction_status(self, extraction_id: int, status: str, 
                               error_message: Optional[str] = None):
        """Update extraction status.
        
        Args:
            extraction_id: Extraction ID (int)
            status: New status
            error_message: Optional error message
        """
        with self.get_session() as session:
            extraction = session.query(Extraction).get(extraction_id)
            
            if extraction:
                extraction.status = status
                extraction.updated_at = datetime.utcnow()
                if error_message:
                    extraction.error_message = error_message
                if status == 'validated':
                    extraction.validation_timestamp = int(time.time())
                session.commit()
                return True
            return False
    
    def update_extraction_source_url(self, extraction_id: int, source_url: str):
        """Update extraction source URL.
        
        Args:
            extraction_id: Extraction ID
            source_url: Source URL to set
        """
        with self.get_session() as session:
            extraction = session.query(Extraction).get(extraction_id)
            if extraction:
                extraction.source_url = source_url
                extraction.updated_at = datetime.utcnow()
                session.commit()
    
    def update_extraction_error(self, extraction_id: int, error_message: str):
        """Update extraction with error message.
        
        Args:
            extraction_id: Extraction ID
            error_message: Error message to set
        """
        with self.get_session() as session:
            extraction = session.query(Extraction).get(extraction_id)
            if extraction:
                extraction.error_message = error_message
                extraction.updated_at = datetime.utcnow()
                session.commit()
    
    # ========================================================================
    # Office Management
    # ========================================================================
    
    def store_extracted_offices(self, extraction_id: int, 
                               offices: List[Dict[str, Any]]) -> List[ExtractedOffice]:
        """Store offices from an extraction.
        
        Args:
            extraction_id: Parent extraction ID
            offices: List of office dictionaries
            
        Returns:
            List[ExtractedOffice]: Created office records
        """
        with self.get_session() as session:
            office_records = []
            for office_data in offices:
                office = ExtractedOffice(
                    extraction_id=extraction_id,
                    **office_data
                )
                session.add(office)
                office_records.append(office)
            session.commit()
            return office_records
    
    def create_extracted_office(self, extraction_id: int, office_data: Dict[str, Any]) -> ExtractedOffice:
        """Create an extracted office record.
        
        Args:
            extraction_id: Parent extraction ID
            office_data: Office data dictionary
            
        Returns:
            ExtractedOffice: Created office record
        """
        with self.get_session() as session:
            office = ExtractedOffice(
                extraction_id=extraction_id,
                **office_data
            )
            session.add(office)
            session.commit()
            return office
    
    def create_validated_office(self, office_data: Dict[str, Any]) -> ValidatedOffice:
        """Create a validated office ready for export.
        
        Args:
            office_data: Office information
            
        Returns:
            ValidatedOffice: Created office
        """
        with self.get_session() as session:
            office = ValidatedOffice(**office_data)
            session.add(office)
            session.commit()
            return office
    
    def get_unsynced_offices(self) -> List[ValidatedOffice]:
        """Get validated offices not yet synced to upstream.
        
        Returns:
            List[ValidatedOffice]: Unsynced offices
        """
        with self.get_session() as session:
            return session.query(ValidatedOffice).filter(
                ValidatedOffice.synced_to_upstream == False
            ).order_by(ValidatedOffice.validated_at).all()
    
    def mark_offices_synced(self, office_ids: List[str]):
        """Mark offices as synced to upstream.
        
        Args:
            office_ids: List of office IDs to mark
        """
        with self.get_session() as session:
            session.query(ValidatedOffice).filter(
                ValidatedOffice.office_id.in_(office_ids)
            ).update({
                'synced_to_upstream': True,
                'synced_at': datetime.utcnow()
            }, synchronize_session=False)
            session.commit()
    
    def get_validated_offices_for_member(self, bioguide_id: str) -> List[ValidatedOffice]:
        """Get validated offices for a specific member.
        
        Args:
            bioguide_id: Member's bioguide ID
            
        Returns:
            List[ValidatedOffice]: Validated offices for the member
        """
        with self.get_session() as session:
            return session.query(ValidatedOffice).filter_by(
                bioguide_id=bioguide_id
            ).all()
    
    # ========================================================================
    # Artifact Management
    # ========================================================================
    
    def store_artifact(self, extraction_id: int, artifact_type: str,
                      filename: str, content: bytes, content_type: str = None,
                      compressed: bool = False) -> int:
        """Store a binary artifact.
        
        Args:
            extraction_id: Parent extraction ID
            artifact_type: Type of artifact
            filename: Original filename
            content: Binary content
            content_type: MIME type
            compressed: Whether content is compressed
            
        Returns:
            int: Created artifact ID
        """
        with self.get_session() as session:
            artifact = Artifact(
                extraction_id=extraction_id,
                artifact_type=artifact_type,
                filename=filename,
                content=content,
                content_type=content_type,
                file_size=len(content),
                compressed=compressed
            )
            session.add(artifact)
            session.commit()
            return artifact.id
    
    def get_artifact(self, extraction_id: int, artifact_type: str) -> Optional[Artifact]:
        """Get a specific artifact.
        
        Args:
            extraction_id: Extraction ID
            artifact_type: Type of artifact
            
        Returns:
            Optional[Artifact]: The artifact if found
        """
        with self.get_session() as session:
            return session.query(Artifact).filter(
                and_(
                    Artifact.extraction_id == extraction_id,
                    Artifact.artifact_type == artifact_type
                )
            ).first()
    
    def get_artifact_content(self, artifact_id: int) -> Optional[bytes]:
        """Get artifact content by ID.
        
        Args:
            artifact_id: Artifact ID
            
        Returns:
            Optional[bytes]: The artifact content if found
        """
        with self.get_session() as session:
            artifact = session.query(Artifact).get(artifact_id)
            return artifact.content if artifact else None
    
    # ========================================================================
    # Cache Management
    # ========================================================================
    
    def get_or_create_cache(self, cache_key: str, cache_type: str,
                           creator_func: callable, expires_in_seconds: int = None) -> bytes:
        """Get from cache or create if not exists.
        
        Args:
            cache_key: Unique cache key
            cache_type: Type of cached data
            creator_func: Function to create content if not cached
            expires_in_seconds: Optional expiration time
            
        Returns:
            bytes: Cached or created content
        """
        with self.get_session() as session:
            # Check cache
            cache_entry = session.query(CacheEntry).filter_by(
                cache_key=cache_key
            ).first()
            
            if cache_entry:
                # Update last accessed
                cache_entry.last_accessed = datetime.utcnow()
                session.commit()
                return cache_entry.content
            
            # Create new cache entry
            content = creator_func()
            
            expires_at = None
            if expires_in_seconds:
                expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)
            
            cache_entry = CacheEntry(
                cache_key=cache_key,
                cache_type=cache_type,
                content=content,
                expires_at=expires_at
            )
            session.add(cache_entry)
            session.commit()
            
            return content
    
    def cleanup_expired_cache(self) -> int:
        """Remove expired cache entries.
        
        Returns:
            int: Number of entries removed
        """
        with self.get_session() as session:
            count = session.query(CacheEntry).filter(
                and_(
                    CacheEntry.expires_at.isnot(None),
                    CacheEntry.expires_at < datetime.utcnow()
                )
            ).delete()
            session.commit()
            return count
    
    # ========================================================================
    # Sync Management
    # ========================================================================
    
    def log_sync_operation(self, sync_type: str, sync_direction: str,
                          records_processed: int, status: str,
                          error_message: Optional[str] = None) -> SyncLog:
        """Log a sync operation.
        
        Args:
            sync_type: Type of sync operation
            sync_direction: Direction of sync
            records_processed: Number of records processed
            status: Operation status
            error_message: Optional error message
            
        Returns:
            SyncLog: Created log entry
        """
        with self.get_session() as session:
            sync_log = SyncLog(
                sync_type=sync_type,
                sync_direction=sync_direction,
                records_processed=records_processed,
                status=status,
                error_message=error_message
            )
            
            if status == 'completed':
                sync_log.completed_at = datetime.utcnow()
            
            session.add(sync_log)
            session.commit()
            return sync_log
    
    def get_last_sync(self, sync_type: str) -> Optional[SyncLog]:
        """Get the last successful sync of a given type.
        
        Args:
            sync_type: Type of sync operation
            
        Returns:
            Optional[SyncLog]: Last successful sync or None
        """
        with self.get_session() as session:
            return session.query(SyncLog).filter(
                and_(
                    SyncLog.sync_type == sync_type,
                    SyncLog.status == 'completed'
                )
            ).order_by(SyncLog.completed_at.desc()).first()
    
    # ========================================================================
    # Cache Management
    # ========================================================================
    
    def store_cache_entry(self, cache_key: str, cache_type: str, content: str, 
                          content_type: str = 'text/plain'):
        """Store content in cache.
        
        Args:
            cache_key: Cache key (usually URL)
            cache_type: Type of cache (html, llm_result, etc.)
            content: Content to cache
            content_type: MIME type
        """
        with self.get_session() as session:
            # Remove existing entry if it exists
            session.query(CacheEntry).filter_by(cache_key=cache_key).delete()
            
            # Create new entry
            cache_entry = CacheEntry(
                cache_key=cache_key,
                cache_type=cache_type,
                content=content.encode('utf-8'),
                content_type=content_type
            )
            session.add(cache_entry)
            session.commit()
    
    def get_cached_content(self, cache_key: str, cache_type: str) -> Optional[str]:
        """Get content from cache.
        
        Args:
            cache_key: Cache key to lookup
            cache_type: Expected cache type
            
        Returns:
            Optional[str]: Cached content if found
        """
        with self.get_session() as session:
            cache_entry = session.query(CacheEntry).filter_by(
                cache_key=cache_key,
                cache_type=cache_type
            ).first()
            
            if not cache_entry:
                return None
            
            # Update last accessed
            cache_entry.last_accessed = datetime.utcnow()
            session.commit()
            
            return cache_entry.content.decode('utf-8')
    
    # ========================================================================
    # Provenance and Logging
    # ========================================================================
    
    def create_provenance_log(self, extraction_id: int, event_type: str, 
                              event_data: Dict[str, Any]) -> int:
        """Create a provenance log entry.
        
        Args:
            extraction_id: Extraction ID
            event_type: Type of event (stored as step_name)
            event_data: Event data as JSON (stored as step_data)
            
        Returns:
            int: Created log ID
        """
        with self.get_session() as session:
            log_entry = ProvenanceLog(
                extraction_id=extraction_id,
                step_name=event_type,
                step_timestamp=int(time.time()),
                step_data=event_data,
                created_at=datetime.utcnow()
            )
            session.add(log_entry)
            session.commit()
            return log_entry.id
    
    # ========================================================================
    # Statistics and Reporting
    # ========================================================================
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get extraction statistics.
        
        Returns:
            Dict[str, Any]: Statistics dictionary
        """
        with self.get_session() as session:
            stats = {}
            
            # Count by status
            for status in ['pending', 'processing', 'validated', 'rejected', 'failed']:
                count = session.query(Extraction).filter(
                    Extraction.status == status
                ).count()
                stats[f'extractions_{status}'] = count
            
            # Count offices
            stats['total_validated_offices'] = session.query(ValidatedOffice).count()
            stats['unsynced_offices'] = session.query(ValidatedOffice).filter(
                ValidatedOffice.synced_to_upstream == False
            ).count()
            
            # Member stats
            stats['total_members'] = session.query(Member).count()
            stats['members_without_offices'] = session.query(Member).filter(
                and_(
                    Member.currentmember == True,
                    ~Member.validated_offices.any()
                )
            ).count()
            
            return stats