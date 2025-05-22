# Async District Office Scraper

This document describes the new asynchronous architecture for extracting district office information from congressional representatives' websites.

## Overview

The async system separates **data extraction** (automated) from **human validation** (interactive) into independent workflows that communicate through a staging directory.

## Components

### 1. Staging Manager (`staging_manager.py`)
- Manages staging directory structure
- Tracks extraction status (pending/validated/rejected/failed)
- Provides cleanup and summary functions

### 2. Async Scraper (`async_scraper.py`)
- Parallel processing of multiple bioguide IDs
- ThreadPoolExecutor for concurrent extraction
- Saves results to staging for later validation

### 3. Validation Runner (`validation_runner.py`)
- Standalone validation processing
- Batch validation capabilities
- Auto-store validated results in database

### 4. Enhanced District Office Scraper (`district_office_scraper.py`)
- Added `--async-mode` flag
- Automatic staging when async mode enabled
- Backward compatible with synchronous operation

## Usage Examples

### Basic Async Workflow

```bash
# Step 1: Extract data asynchronously (no human interaction)
python district_office_scraper.py --bioguide-id A000001 --async-mode

# Step 2: Validate the extraction interactively  
python validation_runner.py --bioguide-id A000001 --auto-store
```

### Batch Processing

```bash
# Extract many bioguides in parallel
python async_scraper.py --all --max-workers 10

# Validate all pending extractions
python validation_runner.py --all-pending --auto-store --batch-size 20
```

### Advanced Usage

```bash
# Custom staging directory
python district_office_scraper.py --all --async-mode --staging-dir /tmp/my_staging

# Process specific bioguides with async scraper
python async_scraper.py --bioguide-ids A000001 A000002 A000003 --max-workers 3

# Force re-processing and validation
python async_scraper.py --bioguide-ids A000001 --force
python validation_runner.py --bioguide-id A000001 --force --auto-store
```

## Directory Structure

```
data/staging/
├── pending/          # Extractions awaiting validation
│   └── A000001_1640995200/
│       ├── extraction.json
│       ├── html_content.html
│       ├── contact_sections.html
│       ├── screenshot.png
│       └── provenance.json
├── validated/        # Human-approved extractions
├── rejected/         # Human-rejected extractions  
├── failed/           # Failed extractions with errors
└── queue.json        # Extraction queue metadata
```

## Benefits

✅ **Parallel Processing**: Extract from multiple sites simultaneously  
✅ **Batch Validation**: Review multiple extractions in sequence  
✅ **Resume Capability**: Validation can happen across multiple sessions  
✅ **Error Recovery**: Failed extractions don't block validation  
✅ **Audit Trail**: Full provenance tracking through staging  
✅ **Backward Compatibility**: Existing synchronous workflow still works

## Migration from Synchronous

The async system is fully backward compatible. Existing commands continue to work:

```bash
# Still works exactly as before
python district_office_scraper.py --bioguide-id A000001
```

To migrate to async:

```bash
# Add --async-mode flag
python district_office_scraper.py --bioguide-id A000001 --async-mode
python validation_runner.py --bioguide-id A000001 --auto-store
```

## Database Integration

Optional database queue tracking is available via:

- `create_extraction_queue_table()`: Create tracking table
- `queue_bioguide_for_extraction()`: Add to queue
- `update_extraction_status()`: Update status
- `get_extraction_queue_summary()`: Queue statistics

## Error Handling

- Failed extractions are saved to `data/staging/failed/`
- Error messages and provenance logs preserved
- Retry capability through `--force` flag
- Cleanup of old processed extractions

## Performance

- Default: 5 concurrent workers (`--max-workers`)
- Staging operations are file-system based (fast)
- Validation HTML generation is cached
- Provenance tracking with minimal overhead