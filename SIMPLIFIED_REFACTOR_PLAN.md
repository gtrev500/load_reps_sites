# Simplified Refactor Plan - No Async Complexity

## Goal: Eliminate DRY Violations Without Async Complexity

Since you're not experienced with async operations, let's focus on **synchronous patterns** that will give you 90% of the benefits with 10% of the complexity.

## Phase 1: Consolidate to Single Synchronous Implementation (Week 1)

### 1.1 Delete the Async Versions
**Boldly eliminate duplication by choosing one path:**

```bash
# Remove these files entirely
rm src/district_offices/core/async_scraper.py
rm src/district_offices/processing/async_llm_processor.py  
rm src/district_offices/storage/async_database.py
rm src/district_offices/validation/async_interface.py
rm cli/async_scrape.py
```

**Benefits:**
- Instantly eliminate ~60% of code duplication
- One codebase to maintain instead of two
- Much easier to understand and debug
- Zero async learning curve

### 1.2 Create Centralized Configuration
```python
# src/district_offices/config.py
class Config:
    """Single source of truth for all configuration"""
    
    # Web scraping settings
    REQUEST_TIMEOUT = 30
    USER_AGENT = "Mozilla/5.0 (compatible; DistrictOfficeScraper/1.0)"
    MAX_HTML_LENGTH = 150000
    
    # LLM settings  
    DEFAULT_MODEL = "claude-3-haiku-20240307"
    MAX_TOKENS = 4000
    
    # Database settings
    CONNECTION_TIMEOUT = 60
    
    # Cache directories
    HTML_CACHE_DIR = "cache/html"
    SCREENSHOT_DIR = "cache/screenshots"
    LLM_RESULTS_DIR = "cache/llm_results"
    
    @classmethod
    def get_db_uri(cls) -> str:
        """Get database URI from environment or config"""
        return os.getenv('DATABASE_URI', 'postgresql://localhost/gov')
```

### 1.3 Extract Common HTML Processing
```python
# src/district_offices/core/html_processor.py
class HTMLProcessor:
    """Centralized HTML processing - easy to understand and test"""
    
    def clean_html(self, html_content: str) -> str:
        """Single implementation of HTML cleaning logic"""
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove unwanted elements
        for element in soup(["script", "style", "path"]):
            element.decompose()
            
        return soup.prettify()
    
    def extract_contact_sections(self, html_content: str) -> List[str]:
        """Single implementation of contact section extraction"""
        soup = BeautifulSoup(html_content, 'html.parser')
        sections = []
        
        # Your existing logic here, but centralized
        contact_keywords = ['district office', 'office location', 'contact', 'address']
        
        for keyword in contact_keywords:
            # Find relevant sections
            elements = soup.find_all(text=lambda t: t and keyword.lower() in t.lower())
            for elem in elements:
                parent = elem.parent
                if parent and str(parent) not in sections:
                    sections.append(str(parent))
                    
        return sections
```

## Phase 2: Simplify Complex Classes (Week 2)

### 2.1 Break Down the Validation Monster
**Your ValidationInterface is 544 lines - let's split it into digestible pieces:**

```python
# src/district_offices/validation/html_generator.py
class ValidationHTMLGenerator:
    """Handles just HTML generation - single responsibility"""
    
    def generate_validation_page(self, bioguide_id: str, offices: List[Dict], 
                                html_content: str, url: str) -> str:
        """Generate HTML for validation - easier to test and modify"""
        return self._build_html_template(bioguide_id, offices, html_content, url)

# src/district_offices/validation/user_interface.py  
class ValidationUI:
    """Handles just user interaction - single responsibility"""
    
    def get_user_decision(self, validation_html_path: str) -> Tuple[bool, List[Dict]]:
        """Get validation decision from user"""
        print(f"Please review: {validation_html_path}")
        decision = input("Accept extraction? (y/n): ").lower()
        return decision == 'y', []

# src/district_offices/validation/validator.py
class OfficeValidator:
    """Coordinates validation process - simple orchestration"""
    
    def __init__(self):
        self.html_generator = ValidationHTMLGenerator()
        self.ui = ValidationUI()
    
    def validate_offices(self, bioguide_id: str, offices: List[Dict], 
                        html_content: str, url: str) -> Tuple[bool, List[Dict]]:
        """Simple, easy-to-understand validation flow"""
        # 1. Generate HTML
        html_path = self.html_generator.generate_validation_page(
            bioguide_id, offices, html_content, url
        )
        
        # 2. Get user decision  
        is_valid, validated_offices = self.ui.get_user_decision(html_path)
        
        # 3. Save result
        if is_valid:
            self._save_validated_data(bioguide_id, offices)
        else:
            self._save_rejected_data(bioguide_id, offices)
            
        return is_valid, validated_offices
```

### 2.2 Create Simple Service Layer
```python
# src/district_offices/services/extraction_service.py
class ExtractionService:
    """Main service - easy to understand flow"""
    
    def __init__(self):
        self.html_processor = HTMLProcessor()
        self.llm_processor = LLMProcessor()
        self.validator = OfficeValidator()
        self.database = DatabaseService()
    
    def extract_offices_for_bioguide(self, bioguide_id: str, 
                                   skip_validation: bool = False) -> bool:
        """Simple, linear flow - easy to follow and debug"""
        
        # 1. Get URL
        url = self.database.get_contact_url(bioguide_id)
        if not url:
            print(f"No URL found for {bioguide_id}")
            return False
        
        # 2. Fetch HTML
        html_content = self._fetch_html(url)
        if not html_content:
            print(f"Failed to fetch HTML for {bioguide_id}")
            return False
        
        # 3. Process HTML
        cleaned_html = self.html_processor.clean_html(html_content)
        sections = self.html_processor.extract_contact_sections(cleaned_html)
        
        # 4. Extract with LLM
        offices = self.llm_processor.extract_offices(sections, bioguide_id)
        if not offices:
            print(f"No offices found for {bioguide_id}")
            return True
        
        # 5. Validate (if requested)
        if not skip_validation:
            is_valid, validated_offices = self.validator.validate_offices(
                bioguide_id, offices, html_content, url
            )
            if not is_valid:
                print(f"Validation failed for {bioguide_id}")
                return False
            offices = validated_offices
        
        # 6. Store results
        success = self.database.store_offices(bioguide_id, offices)
        if success:
            print(f"Successfully processed {bioguide_id}")
        
        return success
```

## Phase 3: Improve Error Handling and Logging (Week 3)

### 3.1 Consistent Error Handling Pattern
```python
# src/district_offices/utils/error_handler.py
class ProcessingError(Exception):
    """Custom exception for processing errors"""
    pass

class ExtractionResult:
    """Simple result object - no async complexity"""
    def __init__(self, success: bool, error_message: str = "", data: Any = None):
        self.success = success
        self.error_message = error_message
        self.data = data
    
    @classmethod
    def success_result(cls, data: Any = None):
        return cls(True, data=data)
    
    @classmethod  
    def error_result(cls, message: str):
        return cls(False, error_message=message)

# Usage in services:
def extract_offices_for_bioguide(self, bioguide_id: str) -> ExtractionResult:
    try:
        # ... processing logic
        return ExtractionResult.success_result(offices)
    except ProcessingError as e:
        return ExtractionResult.error_result(str(e))
    except Exception as e:
        return ExtractionResult.error_result(f"Unexpected error: {str(e)}")
```

## Benefits of This Approach

### ✅ **Eliminates DRY Violations**
- Single implementation instead of sync/async duplicates
- Centralized configuration and HTML processing  
- Shared error handling patterns

### ✅ **Much Easier to Understand**
- Linear, top-to-bottom execution flow
- No async/await complexity
- Easy to debug with print statements and standard debugger

### ✅ **Still Professional and Maintainable**  
- Clear separation of concerns
- Single responsibility classes
- Consistent error handling
- Easy to test individual components

### ✅ **Gradual Improvement Path**
- You can always add async later when you're ready
- Each phase builds on the previous one
- No big-bang rewrites

## Next Steps

1. **Start with Phase 1.1**: Delete the async files to immediately eliminate duplication
2. **Phase 1.2**: Create the config.py file to centralize settings
3. **Phase 1.3**: Extract HTML processing into a simple class

This approach gives you most of the architectural benefits without any async learning curve. You'll have cleaner, more maintainable code that's much easier to work with.

Would you like me to help you implement Phase 1.1 first? We can literally start by safely removing the async versions of files to immediately simplify your codebase. 