# Testing Guide

This guide explains how to write and organize tests in the Testing Service.

## Test Organization

### Directory Structure

```
app/tests/
├── __init__.py
├── test_indexing.py      # Indexing Service tests
├── test_agent.py         # Agent Service tests
├── test_orchestrator.py  # Orchestrator Service tests
└── test_e2e.py          # End-to-end tests
```

### Test Data

```
app/data/
├── test_documents/       # Test PDF files
└── test_queries.json    # Test queries with expected results
```

## Writing Tests

### Basic Test Structure

```python
import pytest
import httpx
from app.config import settings


class TestMyService:
    """Tests for My Service."""

    @pytest.fixture
    def service_url(self):
        """Get service URL."""
        return settings.my_service_url

    def test_health(self, service_url):
        """Test health check."""
        response = httpx.get(f"{service_url}/health", timeout=10.0)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_api_endpoint(self, service_url):
        """Test API endpoint."""
        response = httpx.post(
            f"{service_url}/api/v1/endpoint",
            json={"key": "value"},
            timeout=30.0
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
```

### Testing Streaming Endpoints

```python
def test_streaming_endpoint(self, service_url):
    """Test SSE streaming endpoint."""
    try:
        with httpx.stream(
            "POST",
            f"{service_url}/api/v1/stream",
            json={"message": "test"},
            timeout=30.0
        ) as response:
            assert response.status_code == 200

            events = []
            for line in response.iter_lines():
                if line.startswith("data: "):
                    events.append(line[6:])
                    if len(events) >= 5:
                        break

            assert len(events) > 0
    except httpx.ReadTimeout:
        # Timeout is acceptable for streaming
        pass
```

### Testing File Uploads

```python
def test_file_upload(self, service_url):
    """Test file upload endpoint."""
    test_file = "app/data/test_documents/test.pdf"

    with open(test_file, "rb") as f:
        files = {"file": ("test.pdf", f, "application/pdf")}
        data = {"config": '{"collection_name": "test"}'}

        response = httpx.post(
            f"{service_url}/api/v1/upload",
            files=files,
            data=data,
            timeout=60.0
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
```

### Using Fixtures

```python
@pytest.fixture
def test_collection(self, indexing_url):
    """Create a test collection and clean up after."""
    collection_name = "test_collection_123"

    # Setup: Create collection
    httpx.post(
        f"{indexing_url}/api/v1/ingest",
        json={
            "file_paths": ["test.pdf"],
            "config": {"collection_name": collection_name}
        }
    )

    yield collection_name

    # Teardown: Delete collection
    httpx.delete(f"{indexing_url}/api/v1/collections/{collection_name}")


def test_with_collection(self, indexing_url, test_collection):
    """Test using the fixture."""
    response = httpx.post(
        f"{indexing_url}/api/v1/retrieve",
        json={
            "query": "test",
            "config": {"collection_name": test_collection}
        }
    )
    assert response.status_code == 200
```

### Skipping Tests Conditionally

```python
@pytest.mark.skipif(
    not os.path.exists("app/data/test_documents/test.pdf"),
    reason="Test file not found"
)
def test_with_file(self):
    """Test that requires a specific file."""
    pass


def test_service_availability(self, service_url):
    """Test that skips if service is not running."""
    try:
        response = httpx.get(f"{service_url}/health", timeout=5.0)
        if response.status_code != 200:
            pytest.skip("Service is not healthy")
    except httpx.ConnectError:
        pytest.skip("Service is not running")

    # Continue with test
    pass
```

## Test Suites

### Adding a New Test Suite

1. Create test file in `app/tests/test_myservice.py`
2. Add suite to `TestSuite` enum in `app/schemas.py`:

```python
class TestSuite(str, Enum):
    """Test suite enum."""
    E2E_PIPELINE = "e2e-pipeline"
    INDEXING = "indexing"
    AGENT = "agent"
    ORCHESTRATOR = "orchestrator"
    MY_SERVICE = "my-service"  # Add new suite
    ALL = "all"
```

3. Update `TestRunner._get_test_file()` in `app/services/test_runner.py`:

```python
def _get_test_file(self, suite: str) -> str:
    """Get test file path based on suite name."""
    suite_map = {
        "indexing": "app/tests/test_indexing.py",
        "agent": "app/tests/test_agent.py",
        "orchestrator": "app/tests/test_orchestrator.py",
        "e2e-pipeline": "app/tests/test_e2e.py",
        "my-service": "app/tests/test_myservice.py",  # Add mapping
        "all": "app/tests/"
    }
    return suite_map.get(suite, "app/tests/")
```

## Best Practices

### 1. Test Independence

Each test should be independent and not rely on other tests:

```python
# GOOD: Independent test
def test_create_collection(self):
    collection_name = f"test_{uuid.uuid4()}"
    # Create and test
    # Clean up

# BAD: Depends on previous test
def test_query_collection(self):
    # Assumes collection from previous test exists
    pass
```

### 2. Timeouts

Always set appropriate timeouts:

```python
# Short timeout for health checks
response = httpx.get(url, timeout=5.0)

# Longer timeout for processing
response = httpx.post(url, json=data, timeout=30.0)

# Very long timeout for file uploads
response = httpx.post(url, files=files, timeout=120.0)
```

### 3. Error Handling

Handle expected errors gracefully:

```python
def test_endpoint(self, service_url):
    """Test endpoint."""
    response = httpx.post(f"{service_url}/api/v1/endpoint", json={})

    # Accept multiple valid status codes
    assert response.status_code in [200, 404, 500]

    # Check specific error cases
    if response.status_code == 404:
        assert "not found" in response.json()["detail"].lower()
```

### 4. Assertions

Use clear, specific assertions:

```python
# GOOD: Specific assertions
assert response.status_code == 200
assert "result" in data
assert len(data["items"]) > 0
assert data["status"] == "success"

# BAD: Vague assertions
assert response
assert data
```

### 5. Test Data

Use realistic test data:

```python
# GOOD: Realistic test data
test_queries = [
    {"query": "如何提交论文？", "expected_keywords": ["提交", "论文"]},
    {"query": "导师如何审核？", "expected_keywords": ["导师", "审核"]}
]

# BAD: Meaningless test data
test_queries = [
    {"query": "test", "expected_keywords": ["test"]},
    {"query": "abc", "expected_keywords": ["abc"]}
]
```

## Running Tests

### Run All Tests

```bash
poetry run pytest app/tests/ -v
```

### Run Specific Suite

```bash
poetry run pytest app/tests/test_indexing.py -v
```

### Run Specific Test

```bash
poetry run pytest app/tests/test_indexing.py::TestIndexingService::test_health -v
```

### Run with Coverage

```bash
poetry run pytest app/tests/ --cov=app --cov-report=html
```

### Run with Verbose Output

```bash
poetry run pytest app/tests/ -vv -s
```

## Debugging Tests

### Print Debug Information

```python
def test_with_debug(self, service_url):
    """Test with debug output."""
    response = httpx.post(url, json=data)

    # Print for debugging
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    assert response.status_code == 200
```

### Use pytest Markers

```python
@pytest.mark.slow
def test_slow_operation(self):
    """Test that takes a long time."""
    pass

# Run only slow tests
# pytest -m slow

@pytest.mark.skip(reason="Not implemented yet")
def test_future_feature(self):
    """Test for future feature."""
    pass
```

## CI/CD Integration

### Example GitHub Actions

```yaml
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - name: Start services
        run: docker-compose up -d

      - name: Wait for services
        run: sleep 30

      - name: Run tests
        run: |
          curl -X POST http://localhost:8003/api/v1/tests/run \
            -H "Content-Type: application/json" \
            -d '{"suite": "all", "config": {}}'

      - name: Get results
        run: |
          curl http://localhost:8003/api/v1/tests/results
```

## Troubleshooting

### Tests Fail Locally But Pass in CI

- Check service URLs in `.env`
- Verify all services are running
- Check for port conflicts

### Timeout Errors

- Increase timeout values
- Check service performance
- Verify network connectivity

### Flaky Tests

- Add retries for network operations
- Use fixtures for setup/teardown
- Ensure test independence

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [httpx documentation](https://www.python-httpx.org/)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
