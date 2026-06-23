# tests/test_metrics.py
"""
Tests for evaluation metrics.
"""
import pytest
from unittest.mock import AsyncMock, patch, Mock
from datetime import datetime


@pytest.mark.asyncio
async def test_metrics_computation():
    """Test that metrics are computed correctly."""
    
    # Create mock signals with proper datetime objects
    mock_signals = []
    for i in range(5):
        signal = Mock()
        signal.evaluated_accurate = True if i % 2 == 0 else False
        signal.is_duplicate = False
        signal.impact_level = "HIGH" if i < 2 else "MEDIUM"
        signal.created_at = datetime(2024, 1, 1)  # Use a real datetime object
        mock_signals.append(signal)
    
    # Mock the session execute result
    mock_result = Mock()
    mock_result.scalars.return_value.all.return_value = mock_signals
    
    # Mock session
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    
    # Mock the session context manager
    mock_session_context = AsyncMock()
    mock_session_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_context.__aexit__ = AsyncMock(return_value=None)
    
    with patch("stratos.eval.metrics.get_db_session_manual") as mock_get_session:
        mock_get_session.return_value = mock_session_context
        
        with patch("stratos.eval.metrics.SignalRepository") as mock_repo_class:
            mock_repo_instance = AsyncMock()
            mock_repo_instance.get_by_run.return_value = mock_signals
            mock_repo_class.return_value = mock_repo_instance
            
            with patch("stratos.eval.metrics.select") as mock_select:
                mock_select.return_value = Mock()
                
                from stratos.eval.metrics import SignalEvaluator
                evaluator = SignalEvaluator()
                metrics = await evaluator.compute_metrics()
                
                # 5 total, 3 accurate out of 5 = 0.6 precision
                assert metrics.total_signals == 5
                assert metrics.evaluated_count == 5
                assert metrics.precision == 0.6