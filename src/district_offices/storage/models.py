#!/usr/bin/env python3
"""
SQLAlchemy models for district offices extraction system.
Separate models for upstream PostgreSQL and local SQLite databases.
"""

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, 
    CheckConstraint, Index, BLOB, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

# Separate base classes for different databases
PostgreSQLBase = declarative_base()
SQLiteBase = declarative_base()


# ============================================================================
# UPSTREAM POSTGRESQL MODELS (Read-only except for district_offices)
# ============================================================================

class UpstreamMember(PostgreSQLBase):
    """Members table in upstream PostgreSQL - READ ONLY"""
    __tablename__ = 'members'
    
    bioguideid = Column(String, primary_key=True)
    currentmember = Column(Boolean, nullable=False)
    officialwebsiteurl = Column(Text)
    firstname = Column(String)
    lastname = Column(String)
    state = Column(String(2))
    # ... other columns we don't need for this app


class UpstreamMemberContact(PostgreSQLBase):
    """Member contact pages in upstream PostgreSQL - READ ONLY"""
    __tablename__ = 'members_contact'
    
    bioguideid = Column(String, primary_key=True)
    contact_page = Column(Text, nullable=False)


class UpstreamDistrictOffice(PostgreSQLBase):
    """District offices in upstream PostgreSQL - WRITE ONLY (for exports)"""
    __tablename__ = 'district_offices'
    
    office_id = Column(String, primary_key=True)
    bioguide_id = Column(String, nullable=False)
    address = Column(Text)
    suite = Column(Text)
    building = Column(Text)
    city = Column(Text)
    state = Column(String(2))
    zip = Column(String(10))
    phone = Column(String(20))
    fax = Column(String(20))
    hours = Column(Text)
    # Note: No foreign key to members since we don't control that table


# ============================================================================
# LOCAL SQLITE MODELS (Full control)
# ============================================================================

class Member(SQLiteBase):
    """Local copy of members for processing"""
    __tablename__ = 'members'
    
    bioguideid = Column(String, primary_key=True)
    currentmember = Column(Boolean, nullable=False)
    officialwebsiteurl = Column(Text)
    name = Column(Text)  # Combined first + last for display
    state = Column(String(2))
    
    # Relationships
    contact = relationship("MemberContact", back_populates="member", uselist=False)
    extractions = relationship("Extraction", back_populates="member")
    validated_offices = relationship("ValidatedOffice", back_populates="member")


class MemberContact(SQLiteBase):
    """Local copy of contact URLs"""
    __tablename__ = 'members_contact'
    
    bioguideid = Column(String, ForeignKey('members.bioguideid'), primary_key=True)
    contact_page = Column(Text, nullable=False)
    last_synced = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    member = relationship("Member", back_populates="contact")


class Extraction(SQLiteBase):
    """Main extraction workflow tracking"""
    __tablename__ = 'extractions'
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processing', 'validated', 'rejected', 'failed')"),
        Index('idx_extraction_status', 'status'),
        Index('idx_extraction_bioguide', 'bioguide_id'),
        Index('idx_extraction_processing', 'status', 'priority', 
              postgresql_where="status IN ('pending', 'processing')")
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    bioguide_id = Column(String, ForeignKey('members.bioguideid'), nullable=False)
    status = Column(String, nullable=False, default='pending')
    extraction_timestamp = Column(Integer, nullable=False)
    validation_timestamp = Column(Integer)
    source_url = Column(Text)
    priority = Column(Integer, default=0)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    member = relationship("Member", back_populates="extractions")
    offices = relationship("ExtractedOffice", back_populates="extraction", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="extraction", cascade="all, delete-orphan")
    provenance_logs = relationship("ProvenanceLog", back_populates="extraction", cascade="all, delete-orphan")
    extraction_metadata = relationship("ExtractionMetadata", back_populates="extraction", uselist=False, cascade="all, delete-orphan")


class ExtractedOffice(SQLiteBase):
    """Offices extracted but not yet validated"""
    __tablename__ = 'extracted_offices'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    extraction_id = Column(Integer, ForeignKey('extractions.id', ondelete='CASCADE'), nullable=False)
    office_type = Column(Text)
    address = Column(Text)
    suite = Column(Text)
    building = Column(Text)
    city = Column(Text)
    state = Column(String(2))
    zip = Column(String(10))
    phone = Column(String(20))
    fax = Column(String(20))
    hours = Column(Text)
    office_id_generated = Column(Text)  # The generated office_id
    
    # Relationships
    extraction = relationship("Extraction", back_populates="offices")


class ValidatedOffice(SQLiteBase):
    """Validated offices ready for upstream sync"""
    __tablename__ = 'validated_offices'
    __table_args__ = (
        Index('idx_validated_offices_sync', 'synced_to_upstream',
              postgresql_where='synced_to_upstream = false'),
    )
    
    office_id = Column(String, primary_key=True)
    bioguide_id = Column(String, ForeignKey('members.bioguideid'), nullable=False)
    address = Column(Text)
    suite = Column(Text)
    building = Column(Text)
    city = Column(Text)
    state = Column(String(2))
    zip = Column(String(10))
    phone = Column(String(20))
    fax = Column(String(20))
    hours = Column(Text)
    validated_at = Column(DateTime, default=datetime.utcnow)
    synced_to_upstream = Column(Boolean, default=False)
    synced_at = Column(DateTime)
    
    # Relationships
    member = relationship("Member", back_populates="validated_offices")


class Artifact(SQLiteBase):
    """Binary artifacts storage for validation and review
    
    Stores:
    - html: Full HTML content from the website
    - cleaned_html: Processed HTML ready for validation display
    - validation_html: Generated HTML page for human validation
    - llm_response: Raw LLM API response
    """
    __tablename__ = 'artifacts'
    __table_args__ = (
        CheckConstraint("artifact_type IN ('html', 'cleaned_html', 'validation_html', 'llm_response')"),
        Index('idx_artifacts_extraction', 'extraction_id', 'artifact_type'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    extraction_id = Column(Integer, ForeignKey('extractions.id', ondelete='CASCADE'), nullable=False)
    artifact_type = Column(String, nullable=False)
    filename = Column(Text, nullable=False)
    content = Column(BLOB, nullable=False)  # Store as binary
    content_type = Column(String)  # MIME type
    file_size = Column(Integer)
    compressed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    extraction = relationship("Extraction", back_populates="artifacts")


class ProvenanceLog(SQLiteBase):
    """Tracking of all processing steps"""
    __tablename__ = 'provenance_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    extraction_id = Column(Integer, ForeignKey('extractions.id', ondelete='CASCADE'), nullable=False)
    process_id = Column(String)
    run_id = Column(String)
    step_name = Column(String, nullable=False)
    step_timestamp = Column(Integer, nullable=False)
    step_data = Column(JSON)  # JSON data for step details
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    extraction = relationship("Extraction", back_populates="provenance_logs")


class CacheEntry(SQLiteBase):
    """Cache for frequently accessed data to avoid redundant operations"""
    __tablename__ = 'cache_entries'
    __table_args__ = (
        CheckConstraint("cache_type IN ('html', 'llm_result', 'processed_data')"),
        Index('idx_cache_key', 'cache_key'),
        Index('idx_cache_expires', 'expires_at', postgresql_where='expires_at IS NOT NULL'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    cache_key = Column(String, unique=True, nullable=False)  # Usually URL or hash
    cache_type = Column(String, nullable=False)
    content = Column(BLOB, nullable=False)
    content_type = Column(String)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_accessed = Column(DateTime, default=datetime.utcnow)


class SyncLog(SQLiteBase):
    """Track sync operations with upstream PostgreSQL"""
    __tablename__ = 'sync_log'
    __table_args__ = (
        CheckConstraint("sync_direction IN ('from_upstream', 'to_upstream')"),
        CheckConstraint("status IN ('started', 'completed', 'failed')"),
        Index('idx_sync_log_recent', 'sync_type', 'completed_at'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(String, nullable=False)  # 'members_import', 'contacts_import', 'offices_export'
    sync_direction = Column(String, nullable=False)
    records_processed = Column(Integer)
    status = Column(String, nullable=False)
    error_message = Column(Text)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)


class ExtractionMetadata(SQLiteBase):
    """Flexible metadata storage for extractions"""
    __tablename__ = 'extraction_metadata'
    
    extraction_id = Column(Integer, ForeignKey('extractions.id', ondelete='CASCADE'), primary_key=True)
    metadata_json = Column(JSON)  # Flexible JSON storage
    
    # Relationships
    extraction = relationship("Extraction", back_populates="extraction_metadata")