# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This component extracts district office information from congressional representatives' websites using web scraping, LLM-based data extraction, and human validation. The system uses a SQLite-based architecture for all intermediate processing, with PostgreSQL only for initial data import and final validated data export.

## Key Commands

### Installation and Setup
```bash
# Install package in development mode  
uv pip install -e .

# Install dependencies
uv pip install -r requirements.txt

# Test migration and setup
python test_sqlite_migration.py
python test_scrape_workflow.py
```

### Primary CLI Commands
```bash
# Process single representative
python cli/scrape.py --bioguide-id A000374

# Process all missing offices
python cli/scrape.py --all

# Use custom database URI and API key
python cli/scrape.py --all --db-uri="postgresql://..." --api-key="sk-..."
```

### Validation Workflow
```bash
# Validate pending extractions
python -m district_offices.validation.runner --all-pending --auto-store

# Validate specific bioguide with browser interface
python -m district_offices.validation.runner --bioguide-id A000374 --browser-validation

# Open multiple validation windows for batch review
python -m district_offices.validation.runner --open-multiple --max-windows 5
```

### Development and Testing
```bash
# Run tests
pytest
pytest tests/test_scraper.py -v  # Specific test file
pytest --cov=district_offices    # With coverage

# Find and store contact pages
python -m district_offices.processing.contact_finder --store-db
```

## Architecture

### SQLite-First Design

The system uses SQLite as the primary storage for all processing workflows:

1. **Data Import**: PostgreSQL → SQLite (members, contacts)
2. **Processing**: All extraction, validation, artifacts stored in SQLite  
3. **Data Export**: SQLite → PostgreSQL (validated district offices)

### Core Components

```
src/district_offices/
├── storage/
│   ├── models.py          # SQLAlchemy ORM models for both databases
│   ├── sqlite_db.py       # SQLite database manager with full CRUD
│   └── postgres_sync.py   # PostgreSQL import/export operations
├── core/
│   └── scraper.py         # HTML extraction with artifact storage
├── processing/
│   ├── llm_processor.py   # LLM extraction with SQLite artifacts
│   └── contact_finder.py  # Contact page discovery
├── validation/
│   ├── interface.py       # Human validation UI with SQLite backend
│   └── runner.py          # Batch validation orchestration
└── utils/
    └── logging.py         # Provenance tracking in SQLite
```

### Data Flow

```
PostgreSQL → SQLite → Extract → Artifacts → Validate → Export → PostgreSQL
(members)    (sync)   (HTML)    (storage)  (human)   (offices) (district_offices)
```

Key principles:
- PostgreSQL touched only at start (import) and end (export)
- All intermediate processing in SQLite with ACID transactions
- Binary artifacts (HTML, LLM responses) stored as BLOBs in SQLite
- Comprehensive provenance tracking for all operations

## Database Integration

### SQLite Tables (Local Processing)
- **members**: Local copy of congressional members
- **member_contacts**: Contact page URLs
- **extractions**: Main workflow tracking with status management
- **extracted_offices**: Raw LLM extraction results
- **validated_offices**: Human-approved offices ready for export
- **artifacts**: Binary storage (HTML, LLM responses, validation files)
- **provenance_logs**: Detailed operation tracking
- **cache_entries**: HTTP response caching

### PostgreSQL Tables (Upstream)
- **members**: Source member data (read-only)
- **members_contact**: Contact page URLs (read-only)
- **district_offices**: Final validated data (write-only for exports)

### Connection Management
```python
# SQLite operations use context managers
from district_offices.storage.sqlite_db import SQLiteDatabase

db = SQLiteDatabase('data/district_offices.db')
with db.get_session() as session:
    members = session.query(Member).filter_by(currentmember=True).all()

# PostgreSQL sync operations
from district_offices.storage.postgres_sync import PostgreSQLSyncManager

sync_manager = PostgreSQLSyncManager(postgres_uri, sqlite_db)
stats = sync_manager.full_sync()  # Import members and contacts
```

## Code Patterns

### Extraction Workflow
```python
from district_offices import ProvenanceTracker
from district_offices.core.scraper import extract_html
from district_offices.processing.llm_processor import LLMProcessor

# Initialize tracking
tracker = ProvenanceTracker()
log_path = tracker.log_process_start(bioguide_id)  # Returns "extraction:{id}"

# Extract with artifacts
html_content, artifact_ref = extract_html(url, extraction_id=extraction_id)

# Process with LLM
processor = LLMProcessor()
offices = processor.extract_district_offices(html_content, bioguide_id, extraction_id)

# Complete tracking
tracker.log_process_end(log_path, "completed")
```

### Validation Workflow
```python
from district_offices.validation.interface import ValidationInterface

# Load from SQLite artifacts
interface = ValidationInterface(browser_validation=True)
is_valid, offices = interface.validate_office_data(
    bioguide_id=bioguide_id,
    offices=extracted_offices,
    html_content=html_content,
    url=source_url,
    extraction_id=extraction_id
)
```

### Backward Compatibility
Legacy functions in `__init__.py` provide compatibility:
```python
# These work exactly as before but use SQLite backend
from district_offices import (
    get_bioguides_without_district_offices,
    store_district_office,
    StagingManager
)
```

## Environment Variables
- `DATABASE_URI`: PostgreSQL connection string for import/export
- `ANTHROPIC_API_KEY`: API key for Claude LLM  
- `SQLITE_DB_PATH`: Custom SQLite database path (optional)

## Testing and Migration

### Migration Verification
```bash
# Test full migration from PostgreSQL
python test_sqlite_migration.py

# Test scraping workflow
python test_scrape_workflow.py
```

### Testing Strategy
- Unit tests with pytest for individual components
- Integration tests for database operations
- Fixtures in `tests/conftest.py` provide mocks
- SQLite in-memory databases for test isolation

## Performance and Scalability

### SQLite Optimizations
- WAL mode enabled for concurrent reads during writes
- Foreign keys enforced for data integrity  
- Binary artifacts stored as BLOBs with compression options
- Automatic cleanup of old extractions and artifacts

### Caching Strategy
- HTTP responses cached in SQLite `cache_entries` table
- LLM responses stored as artifacts to avoid re-processing
- Provenance logs maintain full audit trail

## Migration from Legacy System

The system maintains backward compatibility while using the new SQLite architecture:
- Old filesystem staging directories replaced by SQLite tables
- Raw SQL operations replaced by SQLAlchemy ORM
- Async components removed for simplicity
- All intermediate files now stored as SQLite BLOBs