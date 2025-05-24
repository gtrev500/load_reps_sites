# SQLite Migration Plan

## Overview

This document outlines the migration strategy from the current hybrid PostgreSQL + filesystem approach to a SQLite-based system for the district offices extraction project.

**Key Architecture Change**: The SQLite database will be used for all processing and workflow management, while PostgreSQL remains for:
1. Initial data ingestion (reading members and contact URLs)
2. Final validated data storage (district_offices table)

No intermediate processing status or data will be written to PostgreSQL during extraction and validation.

## Current System Analysis

### Current Data Storage
- **PostgreSQL**: Core entities (members, district_offices, extraction_queue)
- **Filesystem**: Staging data, artifacts (HTML, screenshots), logs, provenance
- **JSON files**: Extraction metadata, queue management

### Data Flow
1. Extraction → Staging directory with JSON metadata
2. Validation → Move between staging subdirectories
3. Final storage → PostgreSQL database

## Migration Strategy

### Phase 1: Database Schema Design with SQLAlchemy ORM

We use SQLAlchemy ORM to define separate models for upstream PostgreSQL (read-only) and local SQLite databases:

#### Upstream PostgreSQL Models (Read-only)
```python
# src/district_offices/storage/models.py

class UpstreamMember(PostgreSQLBase):
    """Members table in upstream PostgreSQL - READ ONLY"""
    __tablename__ = 'members'
    
    bioguideid = Column(String, primary_key=True)
    currentmember = Column(Boolean, nullable=False)
    officialwebsiteurl = Column(Text)
    firstname = Column(String)
    lastname = Column(String)
    state = Column(String(2))

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
```

#### Local SQLite Models (Full Control)
```python
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

class Extraction(SQLiteBase):
    """Main extraction workflow tracking"""
    __tablename__ = 'extractions'
    
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

class ValidatedOffice(SQLiteBase):
    """Validated offices ready for upstream sync"""
    __tablename__ = 'validated_offices'
    
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
```

### Phase 2: Data Migration Implementation ✅ COMPLETED

#### What We Did:

1. **Created SQLAlchemy Models** (`src/district_offices/storage/models.py`):
   - Separate models for upstream PostgreSQL (prefixed with `Upstream*`)
   - Complete SQLite models with relationships
   - Clear separation between read-only upstream and local processing

2. **Created SQLite Database Manager** (`src/district_offices/storage/sqlite_db.py`):
   - Full ORM-based database operations
   - Session management with automatic cleanup
   - Methods for all CRUD operations
   - Built-in artifact storage as BLOBs

3. **Created PostgreSQL Sync Manager** (`src/district_offices/storage/postgres_sync.py`):
   - Import members and contacts from upstream
   - Export validated offices to upstream
   - Full sync operations with logging

4. **Updated Dependencies**:
   - Added `sqlalchemy>=2.0.23` to requirements.txt
   - Removed `playwright` (using artifacts instead of browser previews)
   - ✅ Installed all dependencies with `uv pip install -r requirements.txt`

#### 2.3 PostgreSQL Integration Points

```python
# Sync functions for PostgreSQL integration (synchronous)
def sync_from_upstream(db_uri: str, sqlite_path: str):
    """Pull latest member and contact data from PostgreSQL"""
    # 1. Connect to both databases
    # 2. Import members table data
    # 3. Import members_contact data
    # 4. Log sync operation
    
def export_to_upstream(sqlite_path: str, db_uri: str):
    """Push validated offices to PostgreSQL district_offices table"""
    # 1. Get unsynced validated offices
    # 2. Batch insert to PostgreSQL
    # 3. Mark as synced in SQLite
    # 4. Log sync operation
```

### Phase 3: Code Refactoring - READY TO IMPLEMENT

#### 3.1 Remove Old Code

Files to delete:
- `src/district_offices/storage/staging.py` - filesystem staging
- `src/district_offices/storage/database.py` - raw SQL operations
- Any async files if they still exist

#### 3.2 Update Existing Code

Modify to use new ORM:
- `cli/scrape.py` - use SQLiteDatabase instead of raw SQL
- `src/district_offices/processing/llm_processor.py` - store results via ORM
- `src/district_offices/validation/interface.py` - read artifacts from SQLite

#### 3.3 Configuration Updates

Update `src/district_offices/config.py`:

```python
class Config:
    # Replace PostgreSQL settings
    @classmethod
    def get_sqlite_db_path(cls) -> str:
        """Get SQLite database file path."""
        return os.getenv('SQLITE_DB_PATH', cls.PROJECT_ROOT / 'data' / 'district_offices.db')
    
    # Remove filesystem directories (keep minimal cache for temp files)
    @classmethod
    def ensure_directories(cls):
        """Create minimal necessary directories."""
        directories = [
            cls.PROJECT_ROOT / 'data',  # For SQLite file
            cls.PROJECT_ROOT / 'temp',  # For temporary files
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
```

### Phase 4: Benefits and Considerations

#### Benefits
1. **Decoupled from upstream**: No PostgreSQL dependencies during processing
2. **Self-contained workflow**: All extraction/validation data in one place
3. **ACID compliance**: All operations in transactions
4. **Backup simplicity**: Single file to backup processing state
5. **Reduced I/O**: No filesystem traversal for querying data
6. **Better data integrity**: Foreign key constraints, CHECK constraints
7. **Clean separation**: PostgreSQL only for initial data and final results

#### Considerations
1. **File size limits**: SQLite can handle large BLOBs, but monitor database size
2. **Concurrent writes**: SQLite has limited concurrent write capability - use WAL mode
3. **Memory usage**: Large BLOBs in memory during operations
4. **Sync complexity**: Need to manage PostgreSQL sync points carefully
5. **Simple implementation**: Using synchronous sqlite3 for simplicity

### Phase 5: Implementation Steps

#### Step 1: Create SQLite Database Module with SQLAlchemy
```python
# src/district_offices/storage/sqlite_db.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager

class SQLiteDatabase:
    """Manages the local SQLite database for district office processing."""
    
    def __init__(self, db_path: str, echo: bool = False):
        self.db_path = db_path
        self.engine = create_engine(
            f'sqlite:///{db_path}',
            echo=echo,
            connect_args={
                'check_same_thread': False,
                'timeout': 30.0
            }
        )
        self.Session = sessionmaker(bind=self.engine)
        self._init_database()
    
    def _init_database(self):
        """Initialize database with all tables and settings."""
        SQLiteBase.metadata.create_all(self.engine)
        
        with self.engine.connect() as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
    
    @contextmanager
    def get_session(self) -> Session:
        """Get a database session with automatic cleanup."""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    # Example methods using ORM:
    def create_extraction(self, bioguide_id: str, source_url: str) -> Extraction:
        with self.get_session() as session:
            extraction = Extraction(
                bioguide_id=bioguide_id,
                source_url=source_url,
                extraction_timestamp=int(time.time()),
                status='pending'
            )
            session.add(extraction)
            session.commit()
            return extraction
    
    def get_members_without_offices(self) -> List[Member]:
        with self.get_session() as session:
            return session.query(Member).filter(
                and_(
                    Member.currentmember == True,
                    ~Member.validated_offices.any()
                )
            ).all()
```

#### Step 2: PostgreSQL Sync Manager
```python
# src/district_offices/storage/postgres_sync.py
class PostgreSQLSyncManager:
    """Manages sync operations between PostgreSQL and SQLite."""
    
    def __init__(self, postgres_uri: str, sqlite_db: SQLiteDatabase):
        self.postgres_uri = postgres_uri
        self.sqlite_db = sqlite_db
        self.pg_engine = create_engine(postgres_uri)
        self.PGSession = sessionmaker(bind=self.pg_engine)
    
    def sync_members_from_upstream(self) -> Dict[str, int]:
        """Import members from PostgreSQL to SQLite."""
        pg_session = self.PGSession()
        
        # Get all current members from PostgreSQL
        upstream_members = pg_session.query(UpstreamMember).filter(
            UpstreamMember.currentmember == True
        ).all()
        
        # Sync to SQLite
        for upstream_member in upstream_members:
            member_data = {
                'bioguideid': upstream_member.bioguideid,
                'currentmember': upstream_member.currentmember,
                'officialwebsiteurl': upstream_member.officialwebsiteurl,
                'name': f"{upstream_member.firstname} {upstream_member.lastname}".strip(),
                'state': upstream_member.state
            }
            self.sqlite_db.upsert_member(member_data)
        
        pg_session.close()
        return {"members_synced": len(upstream_members)}
    
    def export_validated_offices(self) -> int:
        """Export validated offices from SQLite to PostgreSQL."""
        offices = self.sqlite_db.get_unsynced_offices()
        if not offices:
            return 0
            
        pg_session = self.PGSession()
        
        for office in offices:
            upstream_office = pg_session.query(UpstreamDistrictOffice).filter_by(
                office_id=office.office_id
            ).first()
            
            if upstream_office:
                # Update existing
                for attr in ['bioguide_id', 'address', 'suite', 'building',
                            'city', 'state', 'zip', 'phone', 'fax', 'hours']:
                    setattr(upstream_office, attr, getattr(office, attr))
            else:
                # Create new
                upstream_office = UpstreamDistrictOffice(
                    office_id=office.office_id,
                    bioguide_id=office.bioguide_id,
                    address=office.address,
                    # ... other fields
                )
                pg_session.add(upstream_office)
        
        pg_session.commit()
        pg_session.close()
        
        # Mark as synced in SQLite
        self.sqlite_db.mark_offices_synced([o.office_id for o in offices])
        
        return len(offices)
```

#### Step 2: Update Dependencies
```txt
# Add to requirements.txt
sqlalchemy>=2.0.23  # ORM for both PostgreSQL and SQLite
```

#### Step 3: Migration Script ✅ DEPENDENCIES INSTALLED

Dependencies have been installed with `uv pip install -r requirements.txt`.

To complete migration:
```bash
# 1. Run initial sync from PostgreSQL
python -c "
from district_offices.storage.sqlite_db import SQLiteDatabase
from district_offices.storage.postgres_sync import PostgreSQLSyncManager
import os

db = SQLiteDatabase('data/district_offices.db')
sync = PostgreSQLSyncManager(os.environ['DATABASE_URI'], db)
stats = sync.full_sync()
print(f'Synced: {stats}')
"

# 2. Delete old directories (if desired)
rm -rf data/staging cache logs/artifacts
```

#### Step 4: Update CI/CD and Deployment
- Update deployment scripts to use SQLite
- Modify backup procedures
- Update monitoring for SQLite database

### Phase 6: Data Flow Architecture

#### Current Flow (Before Migration)
```
PostgreSQL → Extract → Filesystem → Validate → PostgreSQL
(members)    (HTML)    (staging)    (human)    (district_offices)
```

#### New Flow (After Migration)
```
PostgreSQL → SQLite → Extract → SQLite → Validate → SQLite → PostgreSQL
(members)    (sync)   (process) (staging) (human)    (export) (district_offices)
```

Key differences:
- PostgreSQL only touched at start (import) and end (export)
- All processing happens in SQLite
- No intermediate PostgreSQL writes

### Phase 7: Testing Strategy

1. **Unit tests**: Test SQLite ORM operations and relationships
2. **Integration tests**: Test PostgreSQL sync functions
3. **End-to-end tests**: Full workflow from import to export
4. **Performance tests**: Compare with current system
5. **Data integrity tests**: Verify sync accuracy and ORM mappings

## Timeline Estimate

- **Phase 1-2** (Schema + Models): ✅ COMPLETED
- **Phase 3** (Code Refactoring): 1-2 weeks  
- **Phase 4-5** (Testing): 1 week
- **Total Remaining**: 2-3 weeks

## Implementation Status

✅ **COMPLETED**:
1. Created SQLAlchemy ORM models with clear separation
2. Implemented SQLite database manager with full ORM support
3. Implemented PostgreSQL sync manager for import/export
4. Updated dependencies (added SQLAlchemy, removed playwright)
5. Installed all dependencies with uv

⏳ **NEXT STEPS**:
1. Delete old filesystem-based code
2. Update CLI and processors to use new ORM
3. Test full workflow from import to export
4. Run initial sync from PostgreSQL

## Next Steps

1. Review this plan focusing on PostgreSQL integration points
2. Validate that contact_finder.py workflow is preserved
3. Design detailed sync protocols for PostgreSQL
4. Begin with synchronous SQLite implementation 