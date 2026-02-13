"""TestRun database model."""
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from app.database import Base


class TestRunStatus(enum.StrEnum):
    """Test run status enum."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TestRun(Base):
    """Test run model."""

    __tablename__ = "test_runs"

    id = Column(Integer, primary_key=True, index=True)
    pr_number = Column(Integer, nullable=False, index=True)
    pr_title = Column(String(500))
    commit_sha = Column(String(40))
    target_hosts = Column(Text, nullable=False)  # Comma-separated IPs/subnets
    target_username = Column(String(100))
    target_password = Column(String(255))  # Stored for re-run convenience (trusted network only)
    protocols = Column(Text)  # Comma-separated protocols (smb,ldap,etc) or empty for all
    kerberos = Column(Integer, default=0)  # Boolean as int
    verbose = Column(Integer, default=0)
    show_errors = Column(Integer, default=0)
    ai_review_enabled = Column(Integer, default=0)  # Boolean as int
    line_nums = Column(Text)  # Comma-separated line numbers/ranges e.g. "5,10-15,20"
    not_tested = Column(Integer, default=0)  # Boolean as int: show commands that didn't get tested
    dns_server = Column(String(255))  # DNS server IP/hostname for Kerberos/domain envs
    status = Column(Enum(TestRunStatus), default=TestRunStatus.QUEUED, nullable=False, index=True)
    celery_task_id = Column(String(255))  # For cancellation
    container_id = Column(String(255))  # For cleanup during cancellation
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    total_tests = Column(Integer, default=0)
    passed_tests = Column(Integer, default=0)
    failed_tests = Column(Integer, default=0)
    ai_review_status = Column(String(20))  # null, "running", "completed", "failed"
    ai_summary = Column(Text)

    # Relationships
    results = relationship("TestResult", back_populates="test_run", cascade="all, delete-orphan")
    logs = relationship("TestLog", back_populates="test_run", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<TestRun(id={self.id}, pr_number={self.pr_number}, status={self.status})>"
