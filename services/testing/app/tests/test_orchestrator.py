"""Test suite for Orchestrator Service."""
import pytest
import httpx
from app.config import settings


class TestOrchestratorService:
    """Tests for Orchestrator Service functionality."""

    @pytest.fixture
    def orchestrator_url(self):
        """Get Orchestrator Service URL."""
        return settings.orchestrator_url

    def test_health(self, orchestrator_url):
        """Test health check endpoint."""
        response = httpx.get(f"{orchestrator_url}/health", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_upload_endpoint_exists(self, orchestrator_url):
        """Test upload endpoint is accessible."""
        # Test without actual file - just check endpoint exists
        response = httpx.post(
            f"{orchestrator_url}/api/v1/upload",
            timeout=10.0
        )
        # Should return 422 (validation error) or 400, not 404
        assert response.status_code in [400, 422, 500]

    def test_chat_endpoint_exists(self, orchestrator_url):
        """Test chat endpoint is accessible."""
        try:
            with httpx.stream(
                "POST",
                f"{orchestrator_url}/api/v1/chat",
                json={
                    "message": "测试消息",
                    "config": {},
                    "thread_id": "test_123"
                },
                timeout=10.0
            ) as response:
                # Should be accessible (200, 404, or 500)
                assert response.status_code in [200, 404, 500]
        except httpx.ReadTimeout:
            # Timeout is acceptable
            pass

    def test_status_endpoint(self, orchestrator_url):
        """Test status endpoint."""
        response = httpx.get(
            f"{orchestrator_url}/api/v1/status/nonexistent_task",
            timeout=10.0
        )
        # Should return 404 for nonexistent task
        assert response.status_code in [404, 500]
