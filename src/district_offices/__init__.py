"""District Offices extraction package."""

from district_offices.core.scraper import (
    extract_html,
    clean_html,
    extract_contact_sections,
    capture_screenshot,
)
from district_offices.processing.llm_processor import LLMProcessor
from district_offices.storage.database import (
    get_db_connection,
    get_contact_page_url,
    get_bioguides_without_district_offices,
    store_district_office,
    check_district_office_exists,
)
from district_offices.storage.staging import (
    StagingManager,
    ExtractionStatus,
    ExtractionData,
)
from district_offices.validation.interface import ValidationInterface
from district_offices.utils.logging import ProvenanceTracker

__version__ = "0.1.0"

__all__ = [
    # Core
    "extract_html",
    "clean_html", 
    "extract_contact_sections",
    "capture_screenshot",
    # Processing
    "LLMProcessor",
    # Storage
    "get_db_connection",
    "get_contact_page_url",
    "get_bioguides_without_district_offices",
    "store_district_office",
    "check_district_office_exists",
    "StagingManager",
    "ExtractionStatus",
    "ExtractionData",
    # Validation
    "ValidationInterface",
    # Utils
    "ProvenanceTracker",
]