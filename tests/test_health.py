# tests/test_health.py
"""
Tests for health check endpoints.
"""
from unittest.mock import patch, AsyncMock


def test_health_check(client):
    """Test that health check returns OK."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_dashboard_public(client):
    """Test that dashboard is publicly accessible."""
    # Mock the database session to avoid connection errors
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)
    
    # Mock the repositories
    with patch("stratos.api.main.get_db_session") as mock_get_db:
        mock_get_db.return_value = mock_session
        
        # Mock the repository methods
        with patch("stratos.api.main.RunRepository") as mock_run_repo:
            mock_run_repo_instance = AsyncMock()
            mock_run_repo_instance.get_latest.return_value = []
            mock_run_repo.return_value = mock_run_repo_instance
            
            with patch("stratos.api.main.SignalRepository") as mock_signal_repo:
                mock_signal_repo_instance = AsyncMock()
                mock_signal_repo_instance.get_count.return_value = 0
                mock_signal_repo_instance.get_high_impact_count.return_value = 0
                mock_signal_repo_instance.get_by_run_with_competitor.return_value = []
                mock_signal_repo_instance.get_latest_for_competitor.return_value = []
                mock_signal_repo.return_value = mock_signal_repo_instance
                
                with patch("stratos.api.main.CompetitorRepository") as mock_comp_repo:
                    mock_comp_repo_instance = AsyncMock()
                    mock_comp_repo_instance.get_all.return_value = []
                    mock_comp_repo.return_value = mock_comp_repo_instance
                    
                    response = client.get("/")
                    assert response.status_code == 200
                    assert "text/html" in response.headers["content-type"]
                    assert "StratOS" in response.text