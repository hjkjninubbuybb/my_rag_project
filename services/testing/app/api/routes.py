"""API routes for Testing Service."""
from fastapi import APIRouter, HTTPException
from typing import List
from app.schemas import (
    TestRunRequest,
    TestRunResponse,
    TestResultsListResponse,
    TestResultDetail,
    TestResultSummary,
    HealthResponse
)
from app.services.test_runner import TestRunner
from app.services.result_storage import ResultStorage
from app.config import settings
from app.utils.logger import logger

router = APIRouter()

# Initialize services lazily
_result_storage = None
_test_runner = None


def get_result_storage():
    """Get or create result storage instance."""
    global _result_storage
    if _result_storage is None:
        _result_storage = ResultStorage(settings.mysql_url)
    return _result_storage


def get_test_runner():
    """Get or create test runner instance."""
    global _test_runner
    if _test_runner is None:
        _test_runner = TestRunner(get_result_storage())
    return _test_runner


@router.post("/api/v1/tests/run", response_model=TestRunResponse)
async def run_tests(request: TestRunRequest):
    """Run a test suite."""
    try:
        logger.info(f"Starting test suite: {request.suite}")
        test_runner = get_test_runner()
        test_run_id = test_runner.run_suite(request.suite.value, request.config)

        # Get the test run to return details
        result_storage = get_result_storage()
        test_run = result_storage.get_test_run(test_run_id)

        return TestRunResponse(
            test_run_id=test_run_id,
            suite=request.suite.value,
            status=test_run.status,
            started_at=test_run.started_at or test_run.created_at
        )
    except Exception as e:
        logger.error(f"Failed to run test suite: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/tests/results", response_model=TestResultsListResponse)
async def get_test_results(limit: int = 50):
    """Get list of test results."""
    try:
        result_storage = get_result_storage()
        test_runs = result_storage.list_test_runs(limit)

        results = []
        for run in test_runs:
            # Extract metrics from result
            passed = None
            failed = None
            if run.result and "metrics" in run.result:
                passed = run.result["metrics"].get("passed")
                failed = run.result["metrics"].get("failed")

            results.append(TestResultSummary(
                id=run.id,
                suite=run.test_suite,
                status=run.status,
                duration_ms=run.duration_ms,
                passed=passed,
                failed=failed,
                finished_at=run.finished_at
            ))

        return TestResultsListResponse(results=results)
    except Exception as e:
        logger.error(f"Failed to get test results: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/tests/results/{test_run_id}", response_model=TestResultDetail)
async def get_test_result(test_run_id: int):
    """Get detailed test result."""
    try:
        result_storage = get_result_storage()
        test_run = result_storage.get_test_run(test_run_id)

        if not test_run:
            raise HTTPException(status_code=404, detail=f"Test run {test_run_id} not found")

        return TestResultDetail(
            id=test_run.id,
            suite=test_run.test_suite,
            status=test_run.status,
            config=test_run.config or {},
            result=test_run.result,
            duration_ms=test_run.duration_ms,
            error_message=test_run.error_message,
            started_at=test_run.started_at,
            finished_at=test_run.finished_at
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get test result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/v1/tests/results/{test_run_id}")
async def delete_test_result(test_run_id: int):
    """Delete a test result."""
    try:
        result_storage = get_result_storage()
        success = result_storage.delete_test_run(test_run_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Test run {test_run_id} not found")

        return {"status": "success", "message": f"Test run {test_run_id} deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete test result: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="ok", service="testing")
