# Modularization Plan for load_reps_sites

## Current Issues
1. **Flat structure**: All Python files at root level makes navigation difficult
2. **Mixed concerns**: Entry points mixed with library code
3. **Tight coupling**: `async_scraper.py` imports from `district_office_scraper.py`
4. **Scattered validation**: Validation logic spread across 3 files
5. **Dual workflow complexity**: Maintaining both sync and async paths adds unnecessary complexity

## Proposed Module Structure

```
load_reps_sites/
├── src/
│   └── district_offices/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── scraper.py          # Web scraping functions
│       │   └── extractor.py        # Contact section extraction logic
│       ├── processing/
│       │   ├── __init__.py
│       │   ├── llm_processor.py    # LLM integration
│       │   └── contact_finder.py   # Contact page discovery
│       ├── storage/
│       │   ├── __init__.py
│       │   ├── database.py         # Database operations
│       │   └── staging.py          # Staging directory management
│       ├── validation/
│       │   ├── __init__.py
│       │   ├── interface.py        # Core validation logic
│       │   ├── server.py           # HTTP server
│       │   └── runner.py           # Batch validation orchestration
│       └── utils/
│           ├── __init__.py
│           └── logging.py          # Logging and provenance tracking
├── cli/
│   ├── __init__.py
│   ├── scrape.py                   # Main async CLI entry point (consolidates both workflows)
│   ├── validate.py                 # Validation CLI (was validation_runner.py)
│   └── find_contacts.py            # Contact finder CLI
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # pytest fixtures and configuration
│   ├── test_scraper.py
│   ├── test_validation.py
│   ├── test_llm_processor.py
│   └── test_integration.py
├── pyproject.toml                  # Modern Python packaging
├── requirements.txt
└── README.md
```

## Migration Steps

### Phase 1: Create Module Structure (Low Risk)
1. Create directory structure
2. Move files to appropriate locations with minimal changes
3. Update imports to use new paths
4. Ensure all existing functionality works

### Phase 2: Refactor Core Issues (Medium Risk)
1. **Consolidate to async-first architecture**:
   - Merge sync and async workflows into single async implementation
   - Use `asyncio.run()` for CLI entry points
   - Extract shared logic into `src/district_offices/core/extractor.py`
   - Remove redundant synchronous code paths
   
2. **Consolidate validation**:
   - Merge validation logic into cohesive module
   - Clear separation: interface.py (UI), server.py (HTTP), runner.py (orchestration)
   - Use async functions throughout validation pipeline

3. **Create async connection pooling**:
   - Add `src/district_offices/storage/connection.py` for shared async DB connections
   - Use `asyncpg` for PostgreSQL async support
   - Reduce connection overhead with connection pool

### Phase 3: Modernize Packaging (Low Risk)
1. Add `pyproject.toml` for modern Python packaging
2. Create proper `__init__.py` files with public API exports
3. Add `setup.py` or use `setuptools` with `pyproject.toml`
4. Enable package installation: `uv pip install -e .`

## Benefits

1. **Clear Architecture**: Module boundaries make the codebase easier to understand
2. **Better Testing**: Can test modules in isolation with pytest
3. **Reduced Coupling**: Shared code in dedicated modules
4. **Maintainability**: Related code grouped together
5. **Professional Structure**: Follows Python packaging best practices
6. **Simplified Workflow**: Single async-first approach eliminates dual-path complexity
7. **Better Performance**: Async operations enable concurrent processing by default

## Example Import Changes

**Before**:
```python
# In district_office_scraper.py
from database import get_contact_url, store_district_offices
from scraper import extract_html, clean_html
```

**After**:
```python
# In cli/scrape.py
from district_offices.storage.database import get_contact_url, store_district_offices
from district_offices.core.scraper import extract_html, clean_html
```

## Breaking Changes

- Import paths will change (can provide migration script)
- CLI entry points will have new names (can keep old names as aliases)
- Need to install package for imports to work: `uv pip install -e .`

## Testing Strategy

This project uses `pytest` for all testing:

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=district_offices --cov-report=html

# Run specific test module
pytest tests/test_scraper.py

# Run with verbose output
pytest -v

# Run only async tests
pytest -k "async"
```

### Test Structure
- `conftest.py`: Shared fixtures for database connections, mock responses, etc.
- Unit tests for each module (test isolation)
- Integration tests for end-to-end workflows
- Async test support with `pytest-asyncio`

## Package Management with uv

This project uses `uv` for Python environment management:

```bash
# Create virtual environment
uv venv

# Activate environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Install dependencies
uv pip install -r requirements.txt

# Install package in development mode
uv pip install -e .

# Install test dependencies
uv pip install pytest pytest-asyncio pytest-cov

# Add new dependencies
uv pip install <package>
uv pip freeze > requirements.txt
```

## Next Steps

1. Review and approve the plan
2. Create feature branch for migration
3. Execute Phase 1 (structure only)
4. Test thoroughly
5. Proceed with Phase 2 (refactoring)
6. Complete Phase 3 (packaging)