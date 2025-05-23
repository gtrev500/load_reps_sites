"""District Offices extraction package."""

# Sync imports (for backward compatibility)
from district_offices.core.scraper import (
    extract_html as sync_extract_html,
    clean_html,
    extract_contact_sections,
    capture_screenshot as sync_capture_screenshot,
)
from district_offices.processing.llm_processor import LLMProcessor

# Async imports (preferred)
from district_offices.core.async_scraper import (
    extract_html,
    capture_screenshot,
    extract_with_playwright,
)
from district_offices.processing.async_llm_processor import AsyncLLMProcessor
from district_offices.storage.async_database import (
    get_connection_pool,
    close_connection_pool,
    check_district_office_exists,
    get_contact_page_url,
    get_bioguides_without_district_offices,
    store_district_office,
)

# Sync database (for backward compatibility)
from district_offices.storage.database import (
    get_db_connection,
    get_contact_page_url as sync_get_contact_page_url,
    get_bioguides_without_district_offices as sync_get_bioguides_without_district_offices,
    store_district_office as sync_store_district_office,
    check_district_office_exists as sync_check_district_office_exists,
)

# Common imports
from district_offices.storage.staging import (
    StagingManager,
    ExtractionStatus,
    ExtractionData,
)
from district_offices.validation.interface import ValidationInterface
from district_offices.utils.logging import ProvenanceTracker

__version__ = "0.1.0"

__all__ = [
    # Async Core (preferred)
    "extract_html",
    "capture_screenshot",
    "extract_with_playwright",
    "clean_html",
    "extract_contact_sections",
    # Async Processing
    "AsyncLLMProcessor",
    # Async Storage
    "get_connection_pool",
    "close_connection_pool",
    "check_district_office_exists",
    "get_contact_page_url",
    "get_bioguides_without_district_offices",
    "store_district_office",
    # Sync (backward compatibility)
    "sync_extract_html",
    "sync_capture_screenshot",
    "LLMProcessor",
    "get_db_connection",
    "sync_get_contact_page_url",
    "sync_get_bioguides_without_district_offices",
    "sync_store_district_office",
    "sync_check_district_office_exists",
    # Common
    "StagingManager",
    "ExtractionStatus",
    "ExtractionData",
    "ValidationInterface",
    "ProvenanceTracker",
]