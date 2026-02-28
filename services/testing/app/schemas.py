"""Pydantic schemas for Testing Service."""
from typing import Dict, Any, List, Optional
from datetime import datetime
from pydantic import BaseModel
from enum import Enum


class TestStatus(str, Enum):
    """Test status enum."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TestSuite(str, Enum):
    """Test suite enum."""
    E2E_PIPELINE = "e2e-pipeline"
    INDEXING = "indexing"
    AGENT = "agent"
    ORCHESTRATOR = "orchestrator"
    ALL = "all"


class TestRunRequest(BaseModel):
    """Request to run a test suite."""
    suite: TestSuite
    config: Dict[str, Any] = {}


class TestRunResponse(BaseModel):
    """Response after starting a test run."""
    test_run_id: int
    suite: str
    status: str
    started_at: datetime


class TestResultSummary(BaseModel):
    """Summary of a test result."""
    id: int
    suite: str
    status: str
    duration_ms: Optional[int] = None
    passed: Optional[int] = None
    failed: Optional[int] = None
    finished_at: Optional[datetime] = None


class TestResultDetail(BaseModel):
    """Detailed test result."""
    id: int
    suite: str
    status: str
    config: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    duration_ms: Optional[int] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class TestResultsListResponse(BaseModel):
    """List of test results."""
    results: List[TestResultSummary]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    service: str
