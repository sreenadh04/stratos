# tests/test_scout.py
"""
Tests for the Scout agent.
"""
import pytest
from unittest.mock import AsyncMock, patch, Mock
from stratos.tools.diff import compute_content_hash


def test_compute_hash():
    """Test content hash computation."""
    content1 = "  Hello World  "
    content2 = "hello world"
    
    hash1 = compute_content_hash(content1)
    hash2 = compute_content_hash(content2)
    
    # Should be the same after normalization
    assert hash1 == hash2


@pytest.mark.asyncio
async def test_scout_competitor_creates_snapshot():
    """Test that scout creates a snapshot for new content."""
    
    mock_competitor_id = "123"
    mock_name = "Test Corp"
    mock_blog_url = "https://test.com/blog"
    mock_run_id = "run-456"
    mock_content = "Test content"
    
    # Mock the scrape_url_async
    with patch("stratos.agents.scout.scrape_url_async") as mock_scrape:
        mock_scraped = Mock()
        mock_scraped.markdown_content = mock_content
        mock_scrape.return_value = mock_scraped
        
        # Mock compute_content_hash
        with patch("stratos.agents.scout.compute_content_hash") as mock_hash:
            mock_hash.return_value = "test_hash_123"
            
            # Mock detect_new_posts to return a post
            with patch("stratos.agents.scout.detect_new_posts") as mock_detect:
                mock_detect.return_value = [{
                    "url": mock_blog_url,
                    "title": mock_name,
                    "content_hash": "test_hash_123",
                    "full_content": mock_content,
                }]
                
                # Mock get_db_session_manual
                with patch("stratos.agents.scout.get_db_session_manual") as mock_session:
                    mock_session_instance = AsyncMock()
                    mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
                    mock_session_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_session.return_value = mock_session_instance
                    
                    # Mock RawSnapshotRepository
                    with patch("stratos.agents.scout.RawSnapshotRepository") as mock_repo:
                        mock_repo_instance = AsyncMock()
                        mock_repo_instance.exists_for_hash.return_value = False
                        mock_snapshot = Mock()
                        mock_snapshot.id = "snapshot-789"
                        mock_repo_instance.create.return_value = mock_snapshot
                        mock_repo.return_value = mock_repo_instance
                        
                        # Import the function (now named scout_competitor_with_retry)
                        from stratos.agents.scout import scout_competitor_with_retry
                        
                        result = await scout_competitor_with_retry(
                            mock_competitor_id,
                            mock_name,
                            mock_blog_url,
                            "blog",
                            mock_run_id
                        )
                        
                        assert len(result) == 1
                        assert result[0]["competitor_name"] == mock_name
                        assert result[0]["snapshot_id"] == "snapshot-789"