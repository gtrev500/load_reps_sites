# District Offices Extraction System

Extract, validate, and managing US congress member's district office information through an automated process of:
1. Web HTML scraping
2. LLM processing
3. and human validation

Purpose is to update [Official Representative District Contact Information](https://github.com/unitedstates/congress-legislators/blob/main/legislators-district-offices.yaml) dataset which is currently slightly incomplete.

## Table of Contents

| Section | Description |
|---------|-------------|
| [Overview](#overview) | System capabilities and features |
| [Installation and Setup](#installation-and-setup) | How to install and initialize the system |
| [Usage](#usage) | Primary CLI commands and examples |
| [Architecture](#architecture) | SQLite-first design and core components |
| [Workflow](#workflow) | Step-by-step data processing flow |
| [LLM Integration](#llm-integration) | Multi-provider LLM support and configuration |
| [Human Validation](#human-validation) | Browser-based validation interface |
| [Configuration](#configuration) | Environment variables and custom settings |
| [Development](#development) | Testing and development workflows |
| [Legacy Compatibility](#legacy-compatibility) | Backward compatibility features |
| [Performance Features](#performance-features) | Caching and optimization strategies |
| [Requirements](#requirements) | System and dependency requirements |
| [Relationship to RepublicReach.org](#relationship-to-republicreachorg) | Integration with larger ecosystem | 

## Overview

This system extracts district office information from congressional representatives' official websites using a modern, SQLite-first architecture with a rigurous validation workflows. The tool provides:

- **Load Members**: Load members from upstream PostgreSQL and populate isolated Sqlite3 database with their website URLs. Data originally sourced from [congress.gov API](https://api.congress.gov/)
- **Web Scraping**: Automated HTML extraction from representative websites with [fallback URL handling](https://github.com/gtrev500/load_reps_sites/blob/master/src/district_offices/utils/url_utils.py#L27)
- **LLM Processing**: Multi-provider LLM integration (Anthropic, OpenAI, Google Gemini) for intelligent data extraction.
- - Gemini 2.5 flash recommended.
- **Human Validation**: Browser-based validation interface with visual highlighting and Accept/Reject workflows
- **SQLite-First Architecture**: Local processing with PostgreSQL sync for production data
- **Comprehensive Provenance**: Full audit trail of all extraction and validation steps
- **Modern CLI**: User-friendly command-line interface with subcommands

## Installation and Setup

### Installation
```bash
pip install -e .
```

### Database Initialization
The SQLite database is automatically created at `./data/district_offices.db` when first run. 

## Usage

### Primary Commands

#### Extract District Office Information
```bash
# Process all representatives without existing office data
district-offices scrape --all [--force]

# Process a specific representative
district-offices scrape --bioguide-id A000374

# Process all representatives without existing office data
district-offices scrape --all

# Force reprocessing of existing data
district-offices scrape --bioguide-id A000374 --force

# Use custom database URI and API key
district-offices scrape --all --db-uri="postgresql://..." --api-key="sk-..."
```

#### Validate Extracted Data
```bash
# Validate all pending extractions (opens browser interface)
district-offices validate --all-pending

# Validate specific representative
district-offices validate --bioguide-id A000374

# Process limited batch with database storage
district-offices validate --all-pending --batch-size 10 --db-uri="postgresql://..."
```

###### Find Contact Pages (deprecated - Checks 301/302/200 STATUS codes @ /contact only)
```bash
# Discover contact pages and store in database
district-offices find-contacts --store-db

# Use custom worker count
district-offices find-contacts --workers 10 --store-db

# Save to file instead of database
district-offices find-contacts -o contacts.txt
```

## Architecture

### SQLite-First Design

The system uses a modern SQLite-first architecture for optimal performance and simplicity:

```
PostgreSQL → SQLite → Extract → Validate → Export → PostgreSQL
(upstream)   (local)  (LLM)    (human)   (sync)   (production)
```

**Benefits:**
- Fast local processing without network dependencies
- ACID transactions for data integrity
- Binary artifact storage (HTML, screenshots, LLM responses)
- Comprehensive audit trail
- Offline capability during processing

### Core Components

```
src/district_offices/
├── storage/
│   ├── models.py          # SQLAlchemy ORM models (PostgreSQL + SQLite)
│   ├── sqlite_db.py       # SQLite database manager with full CRUD
│   └── postgres_sync.py   # PostgreSQL import/export operations
├── core/
│   └── scraper.py         # HTML extraction with caching and artifacts
├── processing/
│   ├── llm_processor.py   # Multi-provider LLM extraction with fallbacks
│   └── contact_finder.py  # Contact page discovery
├── validation/
│   ├── interface.py       # HTML generation for human validation
│   ├── runner.py          # Batch validation orchestration
│   └── server.py          # HTTP server for browser-based validation
├── utils/
│   ├── html.py           # HTML cleaning and processing
│   ├── logging.py        # Provenance tracking
│   └── url_utils.py      # URL pattern generation
└── config.py             # Centralized configuration
```

### Data Models

**SQLite Tables (Local Processing):**
- `members`: Local copy of congressional members
- `extractions`: Main workflow tracking with status management
- `extracted_offices`: Raw LLM extraction results  
- `validated_offices`: Human-approved offices ready for export
- `artifacts`: Binary storage (HTML, LLM responses, validation files)
- `provenance_logs`: Detailed operation tracking
- `cache_entries`: HTTP response caching

**PostgreSQL Tables (Production):**
- `members`: Source member data (read-only)
- `members_contact`: Contact page URLs (read-only)  
- `district_offices`: Final validated data (write-only for exports)

## Workflow

### 1. Data Import (automatic)
```bash
# Automatically syncs from upstream PostgreSQL
district-offices scrape --all
```

### 2. Extraction Process
1. **URL Discovery**: Generate fallback URLs (/contact, /offices, /locations, etc.)
2. **HTML Extraction**: Fetch and cache HTML content with artifact storage
3. **LLM Processing**: Extract office information using intelligent prompts
4. **Artifact Storage**: Save all intermediate files for review and debugging

### 3. Validation Workflow
1. **Browser Interface**: Visual HTML with extracted data highlighted
2. **Human Review**: Accept/Reject individual offices with visual confirmation
3. **Database Storage**: Validated offices stored locally for batch export

### 4. Data Export
```bash
# Export validated offices to PostgreSQL (when `db-uri` provided)
district-offices validate --all-pending --db-uri="postgresql://..."

# if no `--db-uri` provided, stages in Sqlite3 until supplied.
```

## LLM Integration

### Multi-Provider Support
The system supports multiple LLM providers through LiteLLM:

- **Anthropic Claude**: `ANTHROPIC_API_KEY`
- **OpenAI GPT**: `OPENAI_API_KEY`  
- **Google Gemini**: `GEMINI_API_KEY`

### Default Configuration
```python
DEFAULT_MODEL = "gemini/gemini-2.5-flash-preview-05-20"
```

### Fallback Handling
- Automatic URL fallbacks for failed extractions (0 offices returned)
- Rate limiting with exponential backoff

## Human Validation

### Browser-Based Interface
- **Visual Highlighting**: Extracted data highlighted in original HTML context
- **Color-Coded Fields**: Different colors for address, phone, city, state, etc.
- **Accept/Reject Workflow**: Individual office validation with immediate feedback
- **Artifact Viewing**: Access to raw HTML, LLM responses, and extraction metadata

### Validation Server
- HTTP server orchestrates browser tabs for validation
- Automatic progression through pending extractions
- Real-time status updates and validation tracking

## Configuration

### Environment Variables
```bash
# Database connections
DATABASE_URI="postgresql://postgres:postgres@localhost:5432/gov"

# LLM API keys (at least one required for extraction)
ANTHROPIC_API_KEY="sk-ant-..."
OPENAI_API_KEY="sk-..."
GEMINI_API_KEY="..."

# Optional overrides
SQLITE_DB_PATH="./custom/path/district_offices.db"
LOG_LEVEL="DEBUG"
```

### Custom Configuration
Override defaults in `src/district_offices/config.py`:
- Request timeouts and user agents
- LLM model selection and parameters
- Database connection settings
- Contact discovery keywords

## Development

### Running Tests
```bash
# Run test suite
pytest

# With coverage
pytest --cov=district_offices

# Specific test file
pytest tests/test_scraper.py -v
```

### Development Workflow
```bash
# Test migration from PostgreSQL
python test_sqlite_migration.py

# Test complete scraping workflow
python test_scrape_workflow.py
```

## Legacy Compatibility

The system maintains backward compatibility through compatibility wrappers:

- **Legacy Functions**: `get_bioguides_without_district_offices()`, `store_district_office()`, etc.
- **Staging Manager**: Wraps SQLite operations for validation runner
- **File-based Artifacts**: Converted to SQLite BLOB storage with metadata

## Performance Features

### Caching Strategy
- HTTP response caching to avoid redundant requests
- LLM response artifacts prevent re-processing
- SQLite WAL mode for concurrent read/write operations

### Optimization
- Bulk database operations with transaction management
- Parallel processing for batch operations
- Intelligent fallback URL generation reduces failed extractions

## Requirements

### System Requirements
- Python 3.8+
- SQLite 3.35+ (for JSON support)
- PostgreSQL 12+ (for production sync)

### Key Dependencies
- `sqlalchemy>=2.0.23`: Modern ORM with async support
- `litellm>=1.0.0`: Multi-provider LLM integration
- `beautifulsoup4>=4.9.0`: HTML parsing and cleaning
- `requests>=2.25.0`: HTTP client with session management
- `psycopg2-binary>=2.9.0`: PostgreSQL adapter

## Relationship to RepublicReach.org:

This component is part of the larger Congressional Information Portal ecosystem:

- **gov-site**: Main Svelte web application displaying the data
- **etl**: Unified ETL framework for congressional data processing
- **load_congress_data**: Bill and legislation data processing
- **load_map_data**: Congressional district boundary data
- **load_state_info**: State government information processing

The district offices component provides the district office location data that powers the representative lookup and contact features in the main web application.
