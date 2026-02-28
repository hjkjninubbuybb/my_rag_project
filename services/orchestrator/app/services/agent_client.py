"""Client for Agent Service."""
import httpx
from typing import AsyncIterator, Dict, Any
from app.utils.logger import logger


class AgentClient:
    """Client for Agent Service API."""

    def __init__(self, base_url: str, timeout: float = 300.0):
        """Initialize Agent client.

        Args:
            base_url: Base URL of Agent Service
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def chat_stream(
        self,
        message: str,
        config: Dict[str, Any],
        thread_id: str
    ) -> AsyncIterator[str]:
        """Call Agent Service for streaming chat.

        Args:
            message: User message
            config: Chat configuration
            thread_id: Thread ID for conversation context

        Yields:
            SSE data lines (without "data: " prefix)
        """
        url = f"{self.base_url}/api/v1/chat"
        payload = {
            "message": message,
            "config": config,
            "thread_id": thread_id
        }

        logger.info(f"Calling Agent Service chat stream: {url}")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        yield line[6:]  # Remove "data: " prefix
                    elif line.strip():  # Non-empty line without prefix
                        yield line

        logger.info("Agent Service chat stream completed")

    def vlm_analyze(
        self,
        image_base64: str,
        image_type: str,
        surrounding_text: str
    ) -> Dict[str, Any]:
        """Call Agent Service for VLM image analysis.

        Args:
            image_base64: Base64 encoded image
            image_type: Type of image (SCREENSHOT, FLOWCHART, etc.)
            surrounding_text: Context text around the image

        Returns:
            VLM analysis result with summary
        """
        url = f"{self.base_url}/api/v1/vlm/analyze"
        payload = {
            "image_base64": image_base64,
            "image_type": image_type,
            "surrounding_text": surrounding_text
        }

        logger.info(f"Calling Agent Service VLM analyze: {url}")

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()
            logger.info("VLM analysis completed")
            return result

    def health_check(self) -> bool:
        """Check if Agent Service is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            url = f"{self.base_url}/health"
            with httpx.Client(timeout=5.0) as client:
                response = client.get(url)
                return response.status_code == 200
        except Exception as e:
            logger.warning(f"Agent Service health check failed: {e}")
            return False
