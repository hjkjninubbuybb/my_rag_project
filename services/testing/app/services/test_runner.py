"""Test runner for executing test suites."""
import pytest
import json
import os
from datetime import datetime
from typing import Dict, Any
from app.services.result_storage import ResultStorage
from app.utils.logger import logger


class TestRunner:
    """Test runner for executing pytest suites."""

    def __init__(self, result_storage: ResultStorage):
        """Initialize test runner."""
        self.result_storage = result_storage

    def run_suite(self, suite: str, config: Dict[str, Any]) -> int:
        """Run a test suite and return test_run_id."""
        # Create test run record
        test_run_id = self.result_storage.create_test_run(suite, config)

        # Update status to running
        self.result_storage.update_status(test_run_id, "running", datetime.now())

        try:
            # Get test file path
            test_file = self._get_test_file(suite)

            # Prepare pytest arguments
            report_file = f"/tmp/report_{test_run_id}.json"
            args = [
                test_file,
                "-v",
                "--json-report",
                f"--json-report-file={report_file}",
                "--tb=short"
            ]

            # Add limit filter if specified
            if config.get("limit"):
                args.extend(["-k", str(config["limit"])])

            # Add verbose flag
            if config.get("verbose"):
                args.append("-vv")

            logger.info(f"Running pytest with args: {args}")

            # Run pytest
            exit_code = pytest.main(args)

            # Read result report
            if os.path.exists(report_file):
                with open(report_file) as f:
                    result = json.load(f)

                # Extract metrics
                duration_ms = int(result.get("duration", 0) * 1000)
                status = "passed" if exit_code == 0 else "failed"

                # Parse test results
                tests = result.get("tests", [])
                passed = sum(1 for t in tests if t.get("outcome") == "passed")
                failed = sum(1 for t in tests if t.get("outcome") == "failed")

                # Add summary to result
                result["metrics"] = {
                    "total": len(tests),
                    "passed": passed,
                    "failed": failed,
                    "exit_code": exit_code
                }

                # Update result
                self.result_storage.update_result(
                    test_run_id,
                    status,
                    result,
                    duration_ms,
                    datetime.now()
                )

                # Cleanup report file
                os.remove(report_file)
            else:
                # No report file - pytest failed to run
                self.result_storage.update_result(
                    test_run_id,
                    "failed",
                    {"error": "No test report generated"},
                    0,
                    datetime.now(),
                    error_message="Pytest failed to generate report"
                )

        except Exception as e:
            logger.error(f"Test run {test_run_id} failed with exception: {e}")
            self.result_storage.update_result(
                test_run_id,
                "failed",
                {"error": str(e)},
                0,
                datetime.now(),
                error_message=str(e)
            )

        return test_run_id

    def _get_test_file(self, suite: str) -> str:
        """Get test file path based on suite name."""
        suite_map = {
            "indexing": "app/tests/test_indexing.py",
            "agent": "app/tests/test_agent.py",
            "orchestrator": "app/tests/test_orchestrator.py",
            "e2e-pipeline": "app/tests/test_e2e.py",
            "all": "app/tests/"
        }
        return suite_map.get(suite, "app/tests/")
