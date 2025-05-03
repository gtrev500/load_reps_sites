# Representative Websites Contact Validator

This repository contains scripts to locate and validate contact pages on congressional representatives' websites for the Congressional Information Portal.

## Overview

Representatives maintain official websites with contact information for constituents. This component:

- Scans official representative websites
- Validates the existence of contact pages
- Stores the URL paths to contact pages in the database
- Extracts district office information from contact pages (NEW)
- Uses LLM for district office data extraction from HTML (NEW)
- Supports human validation of extracted information (NEW)
- Tracks detailed provenance of data extraction (NEW)

## Key Files and Directories

- `contact_page_finder.py`: Python script that validates the existence of contact pages
- `district_office_scraper.py`: NEW script for extracting district office information
- `database.py`: Database interaction module
- `scraper.py`: HTML extraction and processing module
- `llm_processor.py`: LLM integration for contact information extraction
- `validation.py`: Human validation interface
- `logging_utils.py`: Detailed logging and provenance tracking
- `sitemaps/check_sitemaps.py`: Script that parses website sitemaps to locate contact page URLs
- `sitemaps/sitemap_parser_output.txt`: Output file with extracted sitemap data

## District Office Scraper Usage

The new district office scraper can be used to extract district office information from representative contact pages:

```bash
# Process a specific bioguide ID
python district_office_scraper.py --bioguide-id=S001150

# Process all bioguide IDs without district office information
python district_office_scraper.py --all

# Skip human validation
python district_office_scraper.py --all --skip-validation

# Skip database storage
python district_office_scraper.py --bioguide-id=S001150 --skip-storage

# Specify database URI
python district_office_scraper.py --all --db-uri="postgresql://postgres:postgres@localhost:5432/gov"

# Specify Anthropic API key
python district_office_scraper.py --all --api-key="your-api-key"

# Enable verbose logging
python district_office_scraper.py --all --verbose
```

## Contact Page Finder Usage

```bash
# Check contact pages on representative websites
python contact_page_finder.py

# Store results in the database
python contact_page_finder.py --store-db

# Specify output file
python contact_page_finder.py -o output.txt
```

## Workflow

The district office scraper follows this workflow:

1. Check if district office information already exists in the database
2. Retrieve the contact page URL from the members_contact table
3. Extract HTML from the contact page
4. Clean and extract relevant sections from the HTML
5. Use the Anthropic LLM to extract district office information
6. Present the extracted information for human validation
7. Store validated information in the database
8. Log detailed provenance information for audit and verification

## Provenance Tracking

The district office scraper includes detailed provenance tracking:

- Each extraction run has a unique ID
- All artifacts (HTML, JSON, screenshots) are stored
- Each step in the process is logged
- Human validation results are saved
- A summary of each run is generated

This provenance information allows for verification of data extraction and helps maintain data integrity.

## Requirements

- Python 3.6+
- requests
- BeautifulSoup4 (for HTML parsing)
- psycopg2 (PostgreSQL adapter for Python)
- anthropic (for LLM integration, optional)
- PostgreSQL database

## Relationship to Other Repositories

This is one of several data loader components in the Congressional Information Portal project:

- **gov-site**: The main Svelte web application that displays the data
- **district_offices**: Imports representative district office location data
- **load_congress_data**: Processes congressional bill and legislation data
- **load_map_data**: Handles geographical data for congressional districts
- **load_state_info**: Retrieves and stores state government information