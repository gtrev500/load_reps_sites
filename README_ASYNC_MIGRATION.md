# Async-First Migration Guide

This document describes the async-first architecture implemented in Phase 2 of the modularization.

## Overview

The codebase has been refactored to use async/await patterns throughout, providing:
- Better performance through concurrent I/O operations
- Efficient database connection pooling
- Parallel processing of multiple representatives
- Non-blocking web scraping and API calls

## New Architecture

### Async Modules

1. **`district_offices.core.async_scraper`**
   - `extract_html()` - Async HTML extraction using aiohttp
   - `capture_screenshot()` - Async screenshot capture with Playwright
   - `extract_with_playwright()` - Async JavaScript rendering

2. **`district_offices.storage.async_database`**
   - Connection pooling with asyncpg
   - All database operations are now async
   - Automatic connection management

3. **`district_offices.processing.async_llm_processor`**
   - `AsyncLLMProcessor` class for async LLM calls
   - Uses litellm's async completion API
   - Async file caching with aiofiles

4. **`district_offices.validation.async_interface`**
   - `AsyncValidationInterface` for async validation
   - Non-blocking browser interaction
   - Async HTML generation

### Unified CLI

The new `district-offices` command is the primary entry point:

```bash
# Process single representative
district-offices --bioguide-id A000123

# Process all missing offices concurrently
district-offices --all --max-concurrent 10

# Save to staging for later validation
district-offices --all --async-mode

# Use browser validation
district-offices --bioguide-id A000123 --browser-validation
```

### Migration from Sync Code

#### Before (Sync):
```python
from district_offices import extract_html, LLMProcessor
from district_offices.storage.database import store_district_office

# Sync code
html, path = extract_html(url)
processor = LLMProcessor()
offices = processor.extract_district_offices(sections, bioguide_id)
store_district_office(office, db_uri)
```

#### After (Async):
```python
from district_offices import extract_html, AsyncLLMProcessor
from district_offices.storage.async_database import store_district_office

# Async code
html, path = await extract_html(url)
processor = AsyncLLMProcessor()
offices = await processor.extract_district_offices(sections, bioguide_id)
await store_district_office(office, db_uri)
```

### Connection Pool Management

The async database module automatically manages a connection pool:

```python
from district_offices.storage.async_database import get_connection_pool, close_connection_pool

# Pool is created automatically on first use
offices = await get_bioguides_without_district_offices(db_uri)

# Close pool when done (important for scripts)
await close_connection_pool()
```

### Performance Benefits

1. **Concurrent Processing**: Process multiple representatives simultaneously
2. **Non-blocking I/O**: Web requests don't block other operations
3. **Connection Pooling**: Reuse database connections efficiently
4. **Parallel API Calls**: Multiple LLM requests can run concurrently

### Testing

Run async tests with pytest:

```bash
# Run all tests including async
pytest

# Run only async tests
pytest tests/test_async_extraction.py

# Run with async debugging
pytest -v --log-cli-level=DEBUG
```

### Backward Compatibility

The sync modules are still available for compatibility:
- Use `sync_extract_html` instead of `extract_html`
- Use `LLMProcessor` instead of `AsyncLLMProcessor`
- Use functions from `district_offices.storage.database` (sync)

However, we recommend migrating to the async versions for better performance.

## Common Patterns

### Running Async Functions from Sync Code

```python
import asyncio

# Run a single async function
result = asyncio.run(extract_html(url))

# Run multiple async functions
async def main():
    results = await asyncio.gather(
        extract_html(url1),
        extract_html(url2),
        extract_html(url3)
    )
    return results

results = asyncio.run(main())
```

### Error Handling

```python
try:
    offices = await processor.extract_district_offices(sections, bioguide_id)
except asyncio.TimeoutError:
    log.error("Operation timed out")
except Exception as e:
    log.error(f"Unexpected error: {e}")
```

### Resource Cleanup

Always close the connection pool in scripts:

```python
try:
    # Your async operations
    await process_representatives()
finally:
    await close_connection_pool()
```