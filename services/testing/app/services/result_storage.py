"""Result storage to MySQL."""
from sqlalchemy import create_engine, Column, Integer, String, JSON, DateTime, Enum as SQLEnum, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.utils.logger import logger

Base = declarative_base()


class TestRun(Base):
    """Test run model."""
    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    test_suite = Column(String(255), nullable=False)
    test_name = Column(String(255), nullable=False)
    status = Column(SQLEnum("pending", "running", "passed", "failed", "skipped"), default="pending")
    config = Column(JSON)
    result = Column(JSON)
    duration_ms = Column(Integer)
    error_message = Column(Text)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)


class ResultStorage:
    """Storage for test results in MySQL."""

    def __init__(self, mysql_url: str):
        """Initialize result storage."""
        self.engine = create_engine(mysql_url, pool_pre_ping=True)
        self.Session = sessionmaker(bind=self.engine)
        self._create_tables()

    def _create_tables(self):
        """Create tables if they don't exist."""
        Base.metadata.create_all(self.engine)
        logger.info("Test runs table initialized")

    def create_test_run(self, suite: str, config: Dict[str, Any]) -> int:
        """Create a new test run record."""
        session = self.Session()
        try:
            test_run = TestRun(
                test_suite=suite,
                test_name=suite,
                status="pending",
                config=config
            )
            session.add(test_run)
            session.commit()
            test_run_id = test_run.id
            logger.info(f"Created test run {test_run_id} for suite {suite}")
            return test_run_id
        finally:
            session.close()

    def update_status(self, test_run_id: int, status: str, started_at: datetime):
        """Update test run status."""
        session = self.Session()
        try:
            test_run = session.query(TestRun).filter_by(id=test_run_id).first()
            if test_run:
                test_run.status = status
                test_run.started_at = started_at
                session.commit()
                logger.info(f"Updated test run {test_run_id} status to {status}")
        finally:
            session.close()

    def update_result(
        self,
        test_run_id: int,
        status: str,
        result: Dict[str, Any],
        duration_ms: int,
        finished_at: datetime,
        error_message: Optional[str] = None
    ):
        """Update test run result."""
        session = self.Session()
        try:
            test_run = session.query(TestRun).filter_by(id=test_run_id).first()
            if test_run:
                test_run.status = status
                test_run.result = result
                test_run.duration_ms = duration_ms
                test_run.finished_at = finished_at
                test_run.error_message = error_message
                session.commit()
                logger.info(f"Updated test run {test_run_id} result: {status}")
        finally:
            session.close()

    def get_test_run(self, test_run_id: int) -> Optional[TestRun]:
        """Get a test run by ID."""
        session = self.Session()
        try:
            return session.query(TestRun).filter_by(id=test_run_id).first()
        finally:
            session.close()

    def list_test_runs(self, limit: int = 50) -> List[TestRun]:
        """List recent test runs."""
        session = self.Session()
        try:
            return session.query(TestRun).order_by(TestRun.created_at.desc()).limit(limit).all()
        finally:
            session.close()

    def delete_test_run(self, test_run_id: int) -> bool:
        """Delete a test run."""
        session = self.Session()
        try:
            test_run = session.query(TestRun).filter_by(id=test_run_id).first()
            if test_run:
                session.delete(test_run)
                session.commit()
                logger.info(f"Deleted test run {test_run_id}")
                return True
            return False
        finally:
            session.close()
