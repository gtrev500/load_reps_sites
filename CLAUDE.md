# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This component extracts district office information from congressional representatives' websites using web scraping, LLM-based data extraction, and human validation. It supports both synchronous and asynchronous workflows.

## Key Commands

### Synchronous Workflow (Extract + Validate in one step)
```bash
# Process single bioguide ID
python district_office_scraper.py --bioguide-id=A000374 --db-uri="postgresql://..." --api-key="..."

# Process all missing district offices
python district_office_scraper.py --all --db-uri="postgresql://..." --api-key="..."

# Use browser-based validation (Accept/Reject buttons)
python district_office_scraper.py --bioguide-id=A000374 --browser-validation

# Skip validation or storage
python district_office_scraper.py --bioguide-id=A000374 --skip-validation --skip-storage
```

### Asynchronous Workflow (Extract first, validate later)
```bash
# Step 1: Extract data to staging (no human interaction)
python async_scraper.py --all --max-workers 10
python district_office_scraper.py --bioguide-id=A000374 --async-mode

# Step 2: Validate from staging (interactive)
python validation_runner.py --all-pending --auto-store --browser-validation
python validation_runner.py --bioguide-id=A000374 --auto-store

# Batch open validation windows for review
python validation_runner.py --open-multiple --max-windows 5 --browser-validation
```

### Testing and Development
```bash
# Run tests without making API calls
python test_scraper.py

# Check contact pages existence
python contact_page_finder.py --store-db

# Install dependencies
pip install -r requirements.txt  # or: uv pip install -r requirements.txt
```

## Architecture

### Core Modules

1. **district_office_scraper.py**: Main entry point for extraction
   - Orchestrates the entire extraction pipeline
   - Supports both sync and async modes via `--async-mode` flag
   - Integrates with browser validation via `--browser-validation` flag

2. **async_scraper.py**: Parallel extraction engine
   - ThreadPoolExecutor for concurrent processing
   - Saves to staging directory for later validation
   - Handles batch processing of multiple bioguide IDs

3. **validation.py** + **validation_server.py**: Human validation system
   - Generates HTML interface showing LLM extraction alongside source
   - Browser-based validation with Accept/Reject buttons (optional)
   - Falls back to terminal input if browser validation times out

4. **staging_manager.py**: Staging directory orchestration
   - Manages extraction lifecycle: pending → validated/rejected
   - Preserves all artifacts (HTML, screenshots, provenance)
   - Enables resume capability across sessions

5. **llm_processor.py**: LLM integration for data extraction
   - Sends cleaned HTML sections to Anthropic Claude
   - Extracts structured district office data
   - Handles API errors and retries

6. **scraper.py**: Web scraping and HTML processing
   - Playwright-based browser automation
   - Takes screenshots for validation
   - Cleans and extracts relevant HTML sections

7. **database.py**: PostgreSQL integration
   - Stores district office information
   - Manages extraction queue (optional)
   - Checks for existing data to avoid duplicates

## Data Flow

1. **Extraction Phase**:
   - Fetch contact URL from database → Download HTML → Clean/extract sections → 
   - Send to LLM → Parse response → Save to staging (async) or continue to validation (sync)

2. **Validation Phase**:
   - Load from staging → Generate validation HTML → Open in browser →
   - User accepts/rejects → Update staging status → Store in database (if accepted)

## Staging Directory Structure
```
data/staging/
├── pending/          # Awaiting validation
├── validated/        # Human-approved
├── rejected/         # Human-rejected
├── failed/           # Extraction errors
└── queue.json        # Metadata
```

## Database Tables

- **district_offices**: Stores validated office information
- **members_contact**: Source URLs for contact pages
- **extraction_queue** (optional): Tracks processing status

## Environment Variables

- `DATABASE_URI`: PostgreSQL connection string
- `ANTHROPIC_API_KEY`: API key for Claude LLM

## Code Style

* Imports: Group standard library, third-party, and local imports
* Function docstrings: Use Google style docstrings with Args/Returns sections
* Type hints: Use typing module annotations for parameters and return values
* Error handling: Use try/except with specific exceptions and logging
* Logging: Use the logging module with appropriate severity levels
* Naming: snake_case for variables/functions, CamelCase for classes
* Modularity: Keep code organized in separate modules by functionality
* Handle API responses carefully with robust error handling for JSON parsing