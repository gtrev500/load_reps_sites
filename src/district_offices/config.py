"""Configuration settings for the district offices extraction package."""

import os
from pathlib import Path

class Config:
    """Single source of truth for all configuration values."""
    
    # === Web Scraping Settings ===
    REQUEST_TIMEOUT = 30
    USER_AGENT = "Mozilla/5.0 (compatible; DistrictOfficeScraper/1.0)"
    MAX_HTML_LENGTH = 150000
    MAX_CONTACT_SECTIONS = 5
    
    # === LLM Settings ===
    DEFAULT_MODEL = "claude-3-haiku-20240307"
    MAX_TOKENS = 4000
    TEMPERATURE = 0.1
    
    # === Database Settings ===
    CONNECTION_TIMEOUT = 60
    
    # === Cache Directories ===
    PROJECT_ROOT = Path(__file__).parent.parent.parent
    CACHE_ROOT = PROJECT_ROOT / "cache"
    HTML_CACHE_DIR = CACHE_ROOT / "html"
    SCREENSHOT_DIR = CACHE_ROOT / "screenshots"
    LLM_RESULTS_DIR = CACHE_ROOT / "llm_results"
    
    # === Data Directories ===
    DATA_ROOT = PROJECT_ROOT / "data" 
    STAGING_DIR = DATA_ROOT / "staging"
    VALIDATED_DIR = STAGING_DIR / "validated"
    REJECTED_DIR = STAGING_DIR / "rejected"
    PENDING_DIR = STAGING_DIR / "pending"
    FAILED_DIR = STAGING_DIR / "failed"
    
    # === Logging ===
    LOGS_ROOT = PROJECT_ROOT / "logs"
    ARTIFACTS_DIR = LOGS_ROOT / "artifacts"
    PROVENANCE_DIR = LOGS_ROOT / "provenance"
    RUNS_DIR = LOGS_ROOT / "runs"
    
    @classmethod
    def get_db_uri(cls) -> str:
        """Get database URI from environment variables or default."""
        return os.getenv(
            'DATABASE_URI', 
            'postgresql://postgres:postgres@localhost:5432/gov'
        )
    
    @classmethod
    def get_api_key(cls, provider: str = "anthropic") -> str:
        """Get API key for the specified provider."""
        if provider.lower() == "anthropic":
            return os.getenv('ANTHROPIC_API_KEY', '')
        elif provider.lower() == "openai":
            return os.getenv('OPENAI_API_KEY', '')
        else:
            return os.getenv(f'{provider.upper()}_API_KEY', '')
    
    @classmethod
    def ensure_directories(cls):
        """Create all necessary directories if they don't exist."""
        directories = [
            cls.CACHE_ROOT,
            cls.HTML_CACHE_DIR,
            cls.SCREENSHOT_DIR, 
            cls.LLM_RESULTS_DIR,
            cls.DATA_ROOT,
            cls.STAGING_DIR,
            cls.VALIDATED_DIR,
            cls.REJECTED_DIR,
            cls.PENDING_DIR,
            cls.FAILED_DIR,
            cls.LOGS_ROOT,
            cls.ARTIFACTS_DIR,
            cls.PROVENANCE_DIR,
            cls.RUNS_DIR,
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def get_contact_keywords(cls) -> list:
        """Get the list of keywords used to identify contact sections."""
        return [
            'district office', 
            'office location', 
            'contact', 
            'address',
            'phone', 
            'fax', 
            'hours', 
            'office hours'
        ]

# Initialize directories when the module is imported
Config.ensure_directories() 