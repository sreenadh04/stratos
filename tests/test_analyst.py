# tests/test_analyst.py
"""
Tests for the Analyst agent.
"""
import pytest
from unittest.mock import AsyncMock, patch, Mock


@pytest.mark.asyncio
async def test_analyst_parses_llm_response():
    """Test that analyst correctly parses LLM JSON response."""
    
    mock_snapshot = {
        "competitor_id": "123",
        "competitor_name": "Test Corp",
        "content": "We're launching a new AI product that will disrupt the market.",
        "snapshot_id": "456"
    }
    
    mock_response = '{"summary": "Test summary", "impact_level": "HIGH", "evidence": "Test evidence", "confidence": 0.9}'
    
    with patch("stratos.agents.analyst.LLMFactory.get_provider") as mock_factory:
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=mock_response)
        mock_provider.get_provider_name.return_value = "groq"
        mock_factory.return_value = mock_provider
        
        # Mock vector store
        with patch("stratos.agents.analyst.QdrantStore") as mock_store:
            mock_store_instance = Mock()
            mock_store_instance.search_similar.return_value = []
            mock_store.return_value = mock_store_instance
            
            # Mock embedding
            with patch("stratos.agents.analyst.embed_text") as mock_embed:
                mock_embed.return_value = [0.1] * 768
                
                # Mock DB session
                with patch("stratos.agents.analyst.get_db_session_manual") as mock_session:
                    mock_session_instance = AsyncMock()
                    mock_session_instance.__aenter__ = AsyncMock(return_value=mock_session_instance)
                    mock_session_instance.__aexit__ = AsyncMock(return_value=None)
                    mock_session.return_value = mock_session_instance
                    
                    # Skip actual DB operations
                    with patch("stratos.agents.analyst.SignalRepository") as mock_repo:
                        mock_repo_instance = AsyncMock()
                        mock_signal = Mock()
                        mock_signal.id = "test_id"
                        mock_repo_instance.create.return_value = mock_signal
                        mock_repo.return_value = mock_repo_instance
                        
                        from stratos.agents.analyst import run_analyst
                        result = await run_analyst([mock_snapshot], "test-run-id")
                        
                        assert len(result) == 1
                        assert result[0]["impact_level"] == "HIGH"
                        assert result[0]["competitor_name"] == "Test Corp"