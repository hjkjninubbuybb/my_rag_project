"""Test script to verify Orchestrator Service structure."""
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        from app.config import settings
        print(f"[OK] Config loaded: indexing_url={settings.indexing_url}")

        from app.schemas import (
            UploadResponse,
            ChatRequest,
            IngestAndChatRequest,
            CollectionInfo,
            HealthResponse,
        )
        print("[OK] Schemas imported")

        from app.services.minio_client import MinIOClient
        print("[OK] MinIOClient imported")

        from app.services.indexing_client import IndexingClient
        print("[OK] IndexingClient imported")

        from app.services.agent_client import AgentClient
        print("[OK] AgentClient imported")

        from app.api.routes import router
        print("[OK] API routes imported")

        from app.main import app
        print("[OK] FastAPI app imported")

        print("\n[SUCCESS] All imports successful!")
        return True

    except Exception as e:
        print(f"\n[ERROR] Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_app_structure():
    """Test FastAPI app structure."""
    print("\nTesting app structure...")

    try:
        from app.main import app

        # Check routes
        routes = [route.path for route in app.routes]
        expected_routes = [
            "/api/v1/upload",
            "/api/v1/chat",
            "/api/v1/ingest-and-chat",
            "/api/v1/collections",
            "/health",
        ]

        for route in expected_routes:
            if route in routes:
                print(f"[OK] Route exists: {route}")
            else:
                print(f"[MISSING] Route missing: {route}")

        print("\n[SUCCESS] App structure verified!")
        return True

    except Exception as e:
        print(f"\n[ERROR] App structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_imports() and test_app_structure()
    sys.exit(0 if success else 1)
