#!/usr/bin/env python3
"""Tests for async extraction functionality."""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from district_offices.core.async_scraper import (
    extract_html,
    clean_html,
    extract_contact_sections,
)
from district_offices.processing.async_llm_processor import AsyncLLMProcessor
from district_offices.storage.async_database import (
    get_connection_pool,
    close_connection_pool,
    check_district_office_exists,
    store_district_office,
)


@pytest.mark.asyncio
async def test_async_html_extraction(mock_html_content):
    """Test async HTML extraction with mocked aiohttp."""
    test_url = "https://example.com/contact"
    
    with patch('aiohttp.ClientSession') as mock_session:
        # Setup mock response
        mock_response = AsyncMock()
        mock_response.text = AsyncMock(return_value=mock_html_content)
        mock_response.raise_for_status = Mock()
        
        # Setup mock session
        mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response
        
        # Test extraction
        html, cache_path = await extract_html(test_url, use_cache=False)
        
        assert html == mock_html_content
        assert cache_path is not None


@pytest.mark.asyncio
async def test_async_llm_extraction(mock_html_content, mock_llm_response):
    """Test async LLM extraction."""
    sections = extract_contact_sections(mock_html_content)
    bioguide_id = "TEST123"
    
    with patch('litellm.acompletion') as mock_completion:
        # Setup mock response
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content=str(mock_llm_response)))]
        mock_completion.return_value = mock_response
        
        # Test extraction
        processor = AsyncLLMProcessor()
        offices = await processor.extract_district_offices(
            sections, 
            bioguide_id,
            use_cache=False
        )
        
        assert offices is not None
        assert len(offices) == 1
        assert offices[0]['bioguide_id'] == bioguide_id


@pytest.mark.asyncio
async def test_async_database_operations(mock_database_uri):
    """Test async database operations."""
    bioguide_id = "TEST123"
    
    with patch('asyncpg.create_pool') as mock_create_pool:
        # Setup mock pool
        mock_pool = AsyncMock()
        mock_conn = AsyncMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
        mock_create_pool.return_value = mock_pool
        
        # Test check exists
        mock_conn.fetchval.return_value = 0
        exists = await check_district_office_exists(bioguide_id, mock_database_uri)
        assert exists is False
        
        # Test store office
        office_data = {
            'bioguide_id': bioguide_id,
            'office_id': 'test_office',
            'office_type': 'District Office',
            'address': '123 Test St',
            'city': 'Test City',
            'state': 'TS',
            'zip': '12345'
        }
        
        mock_conn.execute.return_value = None
        success = await store_district_office(office_data, mock_database_uri)
        assert success is True
        
        # Cleanup
        await close_connection_pool()


@pytest.mark.asyncio
async def test_clean_html():
    """Test HTML cleaning (sync function but used in async context)."""
    dirty_html = """
    <html>
    <head>
        <script>alert('test');</script>
        <style>body { color: red; }</style>
    </head>
    <body>
        <!-- Comment -->
        <div>Contact Information</div>
    </body>
    </html>
    """
    
    cleaned = clean_html(dirty_html)
    
    assert '<script>' not in cleaned
    assert '<style>' not in cleaned
    assert '<!-- Comment -->' not in cleaned
    assert 'Contact Information' in cleaned


@pytest.mark.asyncio
async def test_extract_contact_sections():
    """Test contact section extraction."""
    html = """
    <html>
    <body>
        <div>
            <h2>District Office</h2>
            <p>123 Main St<br>
            Springfield, IL 62701<br>
            Phone: (217) 555-0123</p>
        </div>
        <div>
            <h3>Contact Us</h3>
            <p>Email: contact@example.com</p>
        </div>
    </body>
    </html>
    """
    
    sections = extract_contact_sections(html)
    
    assert len(sections) >= 1
    assert 'District Office' in sections[0]
    assert '123 Main St' in sections[0]


@pytest.mark.asyncio
async def test_concurrent_processing():
    """Test concurrent processing of multiple bioguides."""
    from cli.async_scrape import process_multiple_bioguides
    
    bioguide_ids = ["TEST1", "TEST2", "TEST3"]
    
    with patch('cli.async_scrape.process_single_bioguide') as mock_process:
        # Setup mock to return success
        async def mock_async_process(*args, **kwargs):
            bioguide_id = args[0]
            return Mock(
                bioguide_id=bioguide_id,
                success=True,
                error_message=None,
                offices_found=2
            )
        
        mock_process.side_effect = mock_async_process
        
        # Test concurrent processing
        tracker = Mock()
        results = await process_multiple_bioguides(
            bioguide_ids,
            "mock_db_uri",
            tracker,
            max_concurrent=2
        )
        
        assert len(results) == 3
        assert all(r.success for r in results.values())
        assert sum(r.offices_found for r in results.values()) == 6


# Fixtures for async tests are in conftest.py