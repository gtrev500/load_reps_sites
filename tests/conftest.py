"""pytest configuration and fixtures for district offices tests."""

import os
import sys
import pytest
import tempfile
import shutil
from unittest.mock import Mock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from district_offices.storage.staging import StagingManager, ExtractionStatus
from district_offices.utils.logging import ProvenanceTracker


@pytest.fixture
def temp_staging_dir():
    """Create a temporary staging directory for tests."""
    temp_dir = tempfile.mkdtemp(prefix="test_staging_")
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def staging_manager(temp_staging_dir):
    """Create a StagingManager instance with temporary directory."""
    return StagingManager(staging_dir=temp_staging_dir)


@pytest.fixture
def mock_database_uri():
    """Provide a mock database URI for tests."""
    return "postgresql://test:test@localhost/test_db"


@pytest.fixture
def mock_llm_response():
    """Mock LLM response for district office extraction."""
    return {
        "offices": [
            {
                "office_type": "District Office",
                "address": "123 Main St",
                "city": "Springfield",
                "state": "IL",
                "zip": "62701",
                "phone": "(217) 555-0123",
                "fax": "(217) 555-0124",
                "hours": "Monday-Friday 9:00 AM - 5:00 PM"
            }
        ]
    }


@pytest.fixture
def mock_html_content():
    """Mock HTML content from a contact page."""
    return """
    <html>
    <head><title>Contact Us</title></head>
    <body>
        <div class="contact-info">
            <h2>District Office</h2>
            <p>123 Main St<br>
            Springfield, IL 62701<br>
            Phone: (217) 555-0123<br>
            Fax: (217) 555-0124</p>
            <p>Office Hours: Monday-Friday 9:00 AM - 5:00 PM</p>
        </div>
    </body>
    </html>
    """


@pytest.fixture
def mock_contact_url():
    """Mock contact page URL."""
    return "https://example.house.gov/contact"


@pytest.fixture
def provenance_tracker(temp_staging_dir):
    """Create a ProvenanceTracker with temporary directories."""
    tracker = ProvenanceTracker()
    # Override directories to use temp paths
    tracker.logs_dir = os.path.join(temp_staging_dir, "logs", "provenance")
    tracker.runs_dir = os.path.join(temp_staging_dir, "logs", "runs")
    tracker.artifacts_dir = os.path.join(temp_staging_dir, "logs", "artifacts")
    os.makedirs(tracker.logs_dir, exist_ok=True)
    os.makedirs(tracker.runs_dir, exist_ok=True)
    os.makedirs(tracker.artifacts_dir, exist_ok=True)
    return tracker


@pytest.fixture
def mock_database_connection():
    """Mock database connection."""
    with patch('psycopg2.connect') as mock_connect:
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        yield mock_conn