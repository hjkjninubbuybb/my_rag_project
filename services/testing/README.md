# Testing Service

Centralized test management for the RAG system.

## Overview

The Testing Service provides a unified interface for running and managing tests across all microservices in the RAG system. It supports multiple test suites, stores results in MySQL, and provides REST APIs for test execution and result retrieval.

## Features

- **Centralized Test Management**: All tests in one place
- **Multiple Test Suites**: Indexing, Agent, Orchestrator, E2E pipeline
- **Result Persistence**: Test results stored in MySQL
- **REST API**: Easy integration with CI/CD pipelines
- **Detailed Reporting**: Comprehensive test metrics and results

## Architecture

```
Testing Service (Port 8003)
├── API Layer (FastAPI)
├── Test Runner (pytest)
├── Result Storage (MySQL)
└── Test Suites
    ├── test_indexing.py
    ├── test_agent.py
    ├── test_orchestrator.py
    └── test_e2e.py
```

## Installation

```bash
cd services/testing
poetry install
```

## Configuration

Create a `.env` file:

```bash
# Service
SERVICE_PORT=8003

# MySQL
MYSQL_URL=mysql+pymysql://rag_user:rag_password@localhost:3306/rag_db

# Service URLs
ORCHESTRATOR_URL=http://localhost:8000
INDEXING_URL=http://localhost:8001
AGENT_URL=http://localhost:8002

# Test data
TEST_DOCUMENTS_DIR=app/data/test_documents
TEST_QUERIES_FILE=app/data/test_queries.json
```

## Usage

### Start the Service

```bash
poetry run python -m app.main
```

### API Endpoints

#### 1. Run Tests

```bash
POST /api/v1/tests/run
```

**Request:**
```json
{
  "suite": "e2e-pipeline",
  "config": {
    "limit": 10,
    "verbose": true
  }
}
```

**Response:**
```json
{
  "test_run_id": 123,
  "suite": "e2e-pipeline",
  "status": "running",
  "started_at": "2024-01-01T00:00:00Z"
}
```

#### 2. Get Test Results

```bash
GET /api/v1/tests/results?limit=50
```

**Response:**
```json
{
  "results": [
    {
      "id": 123,
      "suite": "e2e-pipeline",
      "status": "passed",
      "duration_ms": 5000,
      "passed": 10,
      "failed": 0,
      "finished_at": "2024-01-01T00:00:05Z"
    }
  ]
}
```

#### 3. Get Test Result Detail

```bash
GET /api/v1/tests/results/{id}
```

**Response:**
```json
{
  "id": 123,
  "suite": "e2e-pipeline",
  "status": "passed",
  "config": {"limit": 10},
  "result": {
    "tests": [...],
    "metrics": {
      "total": 10,
      "passed": 10,
      "failed": 0
    }
  },
  "duration_ms": 5000,
  "started_at": "2024-01-01T00:00:00Z",
  "finished_at": "2024-01-01T00:00:05Z"
}
```

#### 4. Delete Test Result

```bash
DELETE /api/v1/tests/results/{id}
```

#### 5. Health Check

```bash
GET /health
```

## Test Suites

### 1. Indexing Service Tests (`test_indexing.py`)

Tests for document ingestion, retrieval, and collection management:
- Health check
- List collections
- Document ingestion
- Retrieval
- Delete collection

### 2. Agent Service Tests (`test_agent.py`)

Tests for LLM/VLM functionality:
- Health check
- VLM image analysis
- Streaming chat
- Chat reset

### 3. Orchestrator Service Tests (`test_orchestrator.py`)

Tests for orchestration layer:
- Health check
- File upload
- Chat endpoint
- Status endpoint

### 4. E2E Pipeline Tests (`test_e2e.py`)

End-to-end tests for complete workflows:
- All services health check
- Full pipeline simulation
- Upload and query flow

## Test Suites

Available test suites:
- `indexing`: Indexing Service tests
- `agent`: Agent Service tests
- `orchestrator`: Orchestrator Service tests
- `e2e-pipeline`: End-to-end pipeline tests
- `all`: Run all test suites

## Examples

### Run E2E Tests

```bash
curl -X POST http://localhost:8003/api/v1/tests/run \
  -H "Content-Type: application/json" \
  -d '{
    "suite": "e2e-pipeline",
    "config": {"limit": 10, "verbose": true}
  }'
```

### Get Recent Results

```bash
curl http://localhost:8003/api/v1/tests/results?limit=10
```

### Get Detailed Result

```bash
curl http://localhost:8003/api/v1/tests/results/123
```

## Test Data

Place test documents in `app/data/test_documents/`:
- PDF files for ingestion tests
- Sample documents for E2E tests

Test queries are defined in `app/data/test_queries.json`.

## Database Schema

The service uses the `test_runs` table in MySQL:

```sql
CREATE TABLE test_runs (
    id INT PRIMARY KEY AUTO_INCREMENT,
    test_suite VARCHAR(255) NOT NULL,
    test_name VARCHAR(255) NOT NULL,
    status ENUM('pending', 'running', 'passed', 'failed', 'skipped'),
    config JSON,
    result JSON,
    duration_ms INT,
    error_message TEXT,
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Development

### Run Tests Locally

```bash
# Run specific test file
poetry run pytest app/tests/test_indexing.py -v

# Run all tests
poetry run pytest app/tests/ -v

# Run with coverage
poetry run pytest app/tests/ --cov=app --cov-report=html
```

### Add New Tests

1. Create test file in `app/tests/`
2. Follow pytest conventions
3. Use httpx for API calls
4. Add test suite to `TestRunner._get_test_file()`

## Troubleshooting

### Services Not Running

Ensure all services are running:
```bash
curl http://localhost:8000/health  # Orchestrator
curl http://localhost:8001/health  # Indexing
curl http://localhost:8002/health  # Agent
```

### MySQL Connection Error

Check MySQL connection:
```bash
mysql -h localhost -u rag_user -prag_password -e "SELECT 1"
```

### Test Failures

Check test logs in the result detail:
```bash
curl http://localhost:8003/api/v1/tests/results/{id}
```

## CI/CD Integration

Example GitHub Actions workflow:

```yaml
- name: Run Tests
  run: |
    curl -X POST http://testing:8003/api/v1/tests/run \
      -H "Content-Type: application/json" \
      -d '{"suite": "all", "config": {}}'
```

## License

Part of the RAG Project.
