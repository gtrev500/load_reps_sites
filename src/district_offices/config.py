"""Configuration settings for the district offices extraction package."""

import os
from pathlib import Path

class Config:
    """Single source of truth for all configuration values."""
    
    # === Web Scraping Settings ===
    REQUEST_TIMEOUT = 30
    USER_AGENT = "Mozilla/5.0 (compatible; DistrictOfficeScraper/1.0)"
    MAX_HTML_LENGTH = 200000
    MAX_CONTACT_SECTIONS = 5
    
    # === LLM Settings ===
    DEFAULT_MODEL = "gemini/gemini-2.5-flash-preview-05-20"
    MAX_TOKENS = 4000
    TEMPERATURE = 0.1
    
    # === Database Settings ===
    CONNECTION_TIMEOUT = 60
    
    # === Project Root ===
    # Use current working directory instead of package location for data files
    PROJECT_ROOT = Path.cwd()
    
    # === Data Directories - Minimal set for SQLite ===
    DATA_ROOT = PROJECT_ROOT / "data" 
    TEMP_DIR = PROJECT_ROOT / "temp"  # For temporary files during processing
    
    
    @classmethod
    def get_db_uri(cls) -> str:
        """Get PostgreSQL database URI from environment variables or default."""
        return os.getenv(
            'DATABASE_URI', 
            'postgresql://postgres:postgres@localhost:5432/gov'
        )
    
    @classmethod
    def get_sqlite_db_path(cls) -> Path:
        """Get SQLite database file path."""
        return Path(os.getenv('SQLITE_DB_PATH', cls.DATA_ROOT / 'district_offices.db'))
    
    @classmethod
    def get_api_key(cls, provider: str = "anthropic") -> str:
        """Get API key for the specified provider."""
        if provider.lower() == "anthropic":
            return os.getenv('ANTHROPIC_API_KEY', '')
        elif provider.lower() == "openai":
            return os.getenv('OPENAI_API_KEY', '')
        elif provider.lower() == "google" or provider.lower() == "gemini":
            return os.getenv('GEMINI_API_KEY', '')
        else:
            return os.getenv(f'{provider.upper()}_API_KEY', '')
    
    @classmethod
    def ensure_directories(cls):
        """Create minimal necessary directories."""
        directories = [
            cls.DATA_ROOT,  # For SQLite database file
            cls.TEMP_DIR,   # For temporary files during processing
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