"""Client for Indexing Service."""
import httpx
from typing import List, Dict, Any
from app.utils.logger import logger


class IndexingClient:
    """Client for Indexing Service API."""

    def __init__(self, base_url: str, timeout: float = 300.0):
        """Initialize Indexing client.

        Args:
            base_url: Base URL of Indexing Service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.client = httpx.Client(timeout=timeout)

    def ingest(self, file_path: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Call Indexing Service to ingest a file.

        Args:
            file_path: MinIO object path (e.g., raw-documents/2024-01-01/file.pdf)
            config: Ingestion configuration

        Returns:
            Ingestion result with node_count, collection_name, etc.
        """
        url = f"{self.base_url}/api/v1/ingest"
        payload = {
            "file_paths": [file_path],
            "config": config
        }

        logger.info(f"Calling Indexing Service: {url}")
        response = self.client.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Indexing completed: {result.get('node_count', 0)} nodes")
        return result

    def retrieve(self, query: str, config: Dict[str, Any], top_k: int = 5) -> Dict[str, Any]:
        """Call Indexing Service to retrieve documents.

        Args:
            query: Search query
            config: Retrieval configuration
            top_k: Number of results to return

        Returns:
            Retrieval results with nodes
        """
        url = f"{self.base_url}/api/v1/retrieve"
        payload = {
            "query": query,
            "config": config,
            "top_k": top_k
        }

        logger.info(f"Calling Indexing Service retrieve: {url}")
        response = self.client.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        logger.info(f"Retrieved {len(result.get('nodes', []))} nodes")
        return result

    def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections.

        Returns:
            List of collection info (name, point_count)
        """
        url = f"{self.base_url}/api/v1/collections"

        logger.info(f"Calling Indexing Service list collections: {url}")
        response = self.client.get(url)
        response.raise_for_status()

        collections = response.json()
        logger.info(f"Found {len(collections)} collections")
        return collections

    def health_check(self) -> bool:
        """Check if Indexing Service is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            url = f"{self.base_url}/health"
            response = self.client.get(url, timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Indexing Service health check failed: {e}")
            return False

    def close(self):
        """Close HTTP client."""
        self.client.close()
