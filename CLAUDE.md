# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This component extracts district office information from congressional representatives' websites using web scraping, LLM-based data extraction, and human validation. The codebase has been modularized and refactored to use an async-first architecture for better performance and scalability.

## Key Commands

### Primary CLI (Async-First)
```bash
# Install package in development mode
uv pip install -e .

# Process single representative
district-offices --bioguide-id A000374

# Process all missing offices concurrently
district-offices --all --max-concurrent 10

# Save to staging for later validation
district-offices --all --async-mode

# Use browser validation
district-offices --bioguide-id A000374 --browser-validation

# Custom database URI and API key
district-offices --all --db-uri="postgresql://..." --api-key="sk-..."
```

### Validation Workflow
```bash
# Validate staged extractions
district-offices-validate --all-pending --auto-store --browser-validation

# Validate specific bioguide
district-offices-validate --bioguide-id A000374 --auto-store

# Open multiple validation windows
district-offices-validate --open-multiple --max-windows 5
```

### Development Commands
```bash
# Run tests
pytest
pytest tests/test_async_extraction.py  # Async tests only
pytest --cov=district_offices          # With coverage

# Check contact pages
district-offices-find-contacts --store-db

# Install dependencies
uv pip install -r requirements.txt
```

## Architecture

### Module Structure
```
src/district_offices/
├── core/               # Web scraping and HTML processing
│   ├── scraper.py     # Sync scraping (legacy)
│   └── async_scraper.py  # Async scraping with aiohttp/playwright
├── processing/         # Data extraction
│   ├── llm_processor.py  # Sync LLM (legacy)
│   ├── async_llm_processor.py  # Async LLM with litellm
│   └── contact_finder.py  # Contact page discovery
├── storage/           # Data persistence
│   ├── database.py    # Sync database (legacy)
│   ├── async_database.py  # Async database with connection pooling
│   └── staging.py     # Staging directory management
├── validation/        # Human validation
│   ├── interface.py   # Sync validation UI
│   ├── async_interface.py  # Async validation UI
│   ├── server.py      # HTTP server for browser validation
│   └── runner.py      # Batch validation orchestration
└── utils/
    └── logging.py     # Provenance tracking
```

### Async-First Design

The codebase uses async/await patterns throughout for:
- **Concurrent Processing**: Process multiple representatives simultaneously via `--max-concurrent`
- **Non-blocking I/O**: Web scraping with aiohttp, database queries with asyncpg
- **Connection Pooling**: Automatic database connection management (10-20 connections)
- **Parallel LLM Calls**: Multiple API requests can run concurrently

### Data Flow

1. **Extraction Phase**:
   - Get contact URLs from database → Download HTML (async) → Clean/extract sections →
   - Send to LLM (async) → Parse response → Save to staging or continue

2. **Validation Phase**:
   - Load from staging → Generate HTML → Browser/terminal validation →
   - Update status → Store in database (async)

### Staging Directory
```
data/staging/
├── pending/      # Awaiting validation
├── validated/    # Human-approved
├── rejected/     # Human-rejected
├── failed/       # Extraction errors
└── queue.json    # Metadata
```

## Database Integration

### Tables
- **district_offices**: Validated office information
- **members_contact**: Source URLs for contact pages
- **extraction_queue**: Optional processing queue

### Connection Management
```python
# Async operations automatically use connection pool
offices = await get_bioguides_without_district_offices(db_uri)

# Always close pool in scripts
await close_connection_pool()
```

## Code Patterns

### Async Function Usage
```python
# Import async versions
from district_offices import extract_html, AsyncLLMProcessor
from district_offices.storage.async_database import store_district_office

# Use with await
html, path = await extract_html(url)
processor = AsyncLLMProcessor()
offices = await processor.extract_district_offices(sections, bioguide_id)
await store_district_office(office, db_uri)
```

### Error Handling
```python
try:
    result = await process_single_bioguide(bioguide_id, db_uri, tracker)
except asyncio.TimeoutError:
    log.error("Operation timed out")
except Exception as e:
    log.error(f"Error: {e}")
finally:
    await close_connection_pool()
```

### Running from Sync Code
```python
import asyncio

# Single async function
result = asyncio.run(extract_html(url))

# Multiple concurrent
results = asyncio.run(asyncio.gather(
    extract_html(url1),
    extract_html(url2)
))
```

## Environment Variables
- `DATABASE_URI`: PostgreSQL connection string
- `ANTHROPIC_API_KEY`: API key for Claude LLM

## Testing
- Uses pytest with asyncio support
- Fixtures in `tests/conftest.py` provide mocks for database, HTML content, LLM responses
- Run `pytest -v` for verbose output, `pytest -k async` for async tests only

## Performance Considerations
- Default max concurrent workers: 5 (adjustable via `--max-concurrent`)
- Database connection pool: 10-20 connections
- HTML/LLM responses are cached to reduce API calls
- Staging operations are file-based for speed

## Migration Notes
- Sync modules available with `sync_` prefix for backward compatibility
- `ThreadPoolExecutor` in old async_scraper.py replaced with true async/await
- New `district-offices` command consolidates all functionality
- Package must be installed: `uv pip install -e .`