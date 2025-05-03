# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

* Run scraper: `python district_office_scraper.py --bioguide-id=<ID> --db-uri="postgresql://postgres:postgres@localhost:5432/gov" --api-key="<API_KEY>"`
* Skip validation: Add `--skip-validation` flag
* Skip storage: Add `--skip-storage` flag
* Test without API calls: `python test_scraper.py`
* Install dependencies: `pip install -r requirements.txt` or `uv pip install -r requirements.txt`

## Code Style

* Imports: Group standard library, third-party, and local imports
* Function docstrings: Use Google style docstrings with Args/Returns sections
* Type hints: Use typing module annotations for parameters and return values
* Error handling: Use try/except with specific exceptions and logging
* Logging: Use the logging module with appropriate severity levels
* Naming: snake_case for variables/functions, CamelCase for classes
* Modularity: Keep code organized in separate modules by functionality
* Handle API responses carefully with robust error handling for JSON parsing