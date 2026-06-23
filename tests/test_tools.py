# tests/test_tools.py
"""
Tests for tools and utilities.
"""
import pytest
from stratos.tools.diff import compute_content_hash


def test_compute_content_hash_handles_whitespace():
    """Test that content hash handles whitespace consistently."""
    content1 = "  Hello World  "
    content2 = "hello world"
    content3 = "HELLO WORLD"
    
    hash1 = compute_content_hash(content1)
    hash2 = compute_content_hash(content2)
    hash3 = compute_content_hash(content3)
    
    assert hash1 == hash2 == hash3


def test_compute_content_hash_differentiates_content():
    """Test that different content produces different hashes."""
    content1 = "Hello World"
    content2 = "Goodbye World"
    
    hash1 = compute_content_hash(content1)
    hash2 = compute_content_hash(content2)
    
    assert hash1 != hash2


@pytest.mark.asyncio
async def test_retry_decorator():
    """Test that retry decorator retries on failure."""
    from stratos.retry import with_retry
    
    attempt_count = 0
    
    @with_retry(max_attempts=3, min_wait=0.1, max_wait=0.5)
    async def failing_function():
        nonlocal attempt_count
        attempt_count += 1
        if attempt_count < 3:
            raise ValueError("Temporary failure")
        return "success"
    
    result = await failing_function()
    assert result == "success"
    assert attempt_count == 3