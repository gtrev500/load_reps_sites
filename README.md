# Representative Websites Contact Validator

This repository contains scripts to locate and validate contact pages on congressional representatives' websites for the Congressional Information Portal.

## Overview

Representatives maintain official websites with contact information for constituents. This component:

- Scans official representative websites
- Validates the existence of contact pages
- Stores the URL paths to contact pages in the database

This performs basic input validation to ensure contact page URLs are properly stored for the main application.

## Key Files and Directories

- `contact_page_finder.py`: Python script that validates the existence of contact pages
- `sitemaps/check_sitemaps.py`: Script that parses website sitemaps to locate contact page URLs
- `sitemaps/sitemap_parser_output.txt`: Output file with extracted sitemap data

## Usage

```bash
# Check sitemaps to locate contact page URLs
python sitemaps/check_sitemaps.py

# Validate contact pages on representative websites
python contact_page_finder.py
```

## Relationship to Other Repositories

This is one of several data loader components in the Congressional Information Portal project:

- **gov-site**: The main Svelte web application that displays the data
- **district_offices**: Imports representative district office location data
- **load_congress_data**: Processes congressional bill and legislation data
- **load_map_data**: Handles geographical data for congressional districts
- **load_state_info**: Retrieves and stores state government information

## Requirements

- Python 3.6+
- requests
- BeautifulSoup4 (for sitemap parsing)
- psycopg2 (PostgreSQL adapter for Python)
- PostgreSQL database