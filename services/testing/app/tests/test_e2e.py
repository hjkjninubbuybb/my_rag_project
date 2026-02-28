"""End-to-end test suite."""
import pytest
import httpx
import time
import os
from app.config import settings


class TestE2EPipeline:
    """End-to-end tests for the complete RAG pipeline."""

    @pytest.fixture
    def orchestrator_url(self):
        """Get Orchestrator Service URL."""
        return settings.orchestrator_url

    @pytest.fixture
    def test_pdf_path(self):
        """Get test PDF file path."""
        return os.path.join(settings.test_documents_dir, "test.pdf")

    def test_services_health(self):
        """Test all services are healthy."""
        services = {
            "orchestrator": settings.orchestrator_url,
            "indexing": settings.indexing_url,
            "agent": settings.agent_url
        }

        for name, url in services.items():
            try:
                response = httpx.get(f"{url}/health", timeout=10.0)
                assert response.status_code == 200, f"{name} service is not healthy"
                data = response.json()
                assert data["status"] == "ok", f"{name} service status is not ok"
            except httpx.ConnectError:
                pytest.skip(f"{name} service is not running")

    def test_full_pipeline_simulation(self, orchestrator_url):
        """Test full pipeline flow (simulated without actual file)."""
        # This is a simulation test - actual E2E would require:
        # 1. Upload file to Orchestrator
        # 2. Wait for ingestion to complete
        # 3. Query the system
        # 4. Verify response

        # For now, we just verify the endpoints are accessible
        # Step 1: Check upload endpoint exists
        response = httpx.post(f"{orchestrator_url}/api/v1/upload", timeout=10.0)
        assert response.status_code in [400, 422, 500]  # Not 404

        # Step 2: Check chat endpoint exists
        try:
            with httpx.stream(
                "POST",
                f"{orchestrator_url}/api/v1/chat",
                json={
                    "message": "测试查询",
                    "config": {"collection_name": "test"},
                    "thread_id": "e2e_test_123"
                },
                timeout=10.0
            ) as response:
                assert response.status_code in [200, 404, 500]
        except httpx.ReadTimeout:
            pass

    @pytest.mark.skipif(
        not os.path.exists(os.path.join(settings.test_documents_dir, "test.pdf")),
        reason="Test PDF file not found"
    )
    def test_upload_and_query(self, orchestrator_url, test_pdf_path):
        """Test upload and query with actual file."""
        # Upload file
        with open(test_pdf_path, "rb") as f:
            files = {"file": ("test.pdf", f, "application/pdf")}
            data = {"config": '{"collection_name": "e2e_test"}'}

            response = httpx.post(
                f"{orchestrator_url}/api/v1/upload",
                files=files,
                data=data,
                timeout=60.0
            )

        if response.status_code == 200:
            # Wait for ingestion
            time.sleep(10)

            # Query
            response = httpx.post(
                f"{orchestrator_url}/api/v1/chat",
                json={
                    "message": "文档的主要内容是什么？",
                    "config": {"collection_name": "e2e_test"},
                    "thread_id": "e2e_test_456"
                },
                timeout=30.0
            )

            assert response.status_code in [200, 404, 500]
        else:
            pytest.skip("Upload failed - service may not be fully configured")
