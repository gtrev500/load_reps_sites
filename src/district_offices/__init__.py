"""District Offices extraction package."""

# Configuration
from district_offices.config import Config

# Core functionality
from district_offices.core.scraper import (
    extract_html,
    capture_screenshot,
)

# Processing 
from district_offices.processing.llm_processor import LLMProcessor

# Storage
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

# Validation
from district_offices.validation.interface import ValidationInterface

# Utils
from district_offices.utils.logging import ProvenanceTracker
from district_offices.utils.html import clean_html

__version__ = "0.1.0"

__all__ = [
    # Configuration
    "Config",
    # Core
    "extract_html",
    "capture_screenshot", 
    # Utils
    "clean_html",
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