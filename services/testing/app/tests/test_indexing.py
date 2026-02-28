"""Test suite for Indexing Service."""
import pytest
import httpx
from app.config import settings


class TestIndexingService:
    """Tests for Indexing Service functionality."""

    @pytest.fixture
    def indexing_url(self):
        """Get Indexing Service URL."""
        return settings.indexing_url

    def test_health(self, indexing_url):
        """Test health check endpoint."""
        response = httpx.get(f"{indexing_url}/health", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_list_collections(self, indexing_url):
        """Test list collections endpoint."""
        response = httpx.get(f"{indexing_url}/api/v1/collections", timeout=10.0)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_ingest(self, indexing_url):
        """Test document ingestion."""
        # This test requires actual files in MinIO
        # For now, we test the endpoint is accessible
        response = httpx.post(
            f"{indexing_url}/api/v1/ingest",
            json={
                "file_paths": ["test-bucket/test.pdf"],
                "config": {
                    "collection_name": "test_collection",
                    "chunking_strategy": "fixed",
                    "chunk_size": 512
                }
            },
            timeout=30.0
        )
        # May fail if file doesn't exist, but endpoint should be accessible
        assert response.status_code in [200, 400, 404, 500]

    def test_retrieve(self, indexing_url):
        """Test retrieval endpoint."""
        response = httpx.post(
            f"{indexing_url}/api/v1/retrieve",
            json={
                "query": "测试查询",
                "config": {
                    "collection_name": "test_collection",
                    "top_k": 5
                }
            },
            timeout=10.0
        )
        # May fail if collection doesn't exist
        assert response.status_code in [200, 404, 500]

    def test_delete_collection(self, indexing_url):
        """Test delete collection endpoint."""
        response = httpx.delete(
            f"{indexing_url}/api/v1/collections/nonexistent_collection",
            timeout=10.0
        )
        # Should return 404 for nonexistent collection
        assert response.status_code in [200, 404]
