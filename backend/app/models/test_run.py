"""TestRun database model."""
from datetime import datetime
import enum

from sqlalchemy import Enum as SAEnum, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

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

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, index=True, default=None)
    branch: Mapped[str | None] = mapped_column(String(255), default=None)
    repo: Mapped[str | None] = mapped_column(String(255), default=None)
    pr_title: Mapped[str | None] = mapped_column(String(500), default=None)
    commit_sha: Mapped[str | None] = mapped_column(String(40), default=None)
    target_hosts: Mapped[str] = mapped_column(Text)
    target_username: Mapped[str | None] = mapped_column(String(100), default=None)
    target_password: Mapped[str | None] = mapped_column(String(255), default=None)  # Stored for re-run convenience (trusted network only)
    protocols: Mapped[str | None] = mapped_column(Text, default=None)  # Comma-separated protocols or empty for all
    kerberos: Mapped[int] = mapped_column(Integer, default=0)  # Boolean as int
    verbose: Mapped[int] = mapped_column(Integer, default=0)
    show_errors: Mapped[int] = mapped_column(Integer, default=0)
    ai_review_enabled: Mapped[int] = mapped_column(Integer, default=0)  # Boolean as int
    line_nums: Mapped[str | None] = mapped_column(Text, default=None)  # Comma-separated line numbers/ranges e.g. "5,10-15,20"
    not_tested: Mapped[int] = mapped_column(Integer, default=0)  # Boolean as int: show commands that didn't get tested
    dns_server: Mapped[str | None] = mapped_column(String(255), default=None)  # DNS server IP/hostname for Kerberos/domain envs
    status: Mapped[TestRunStatus] = mapped_column(SAEnum(TestRunStatus), default=TestRunStatus.QUEUED, index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), default=None)  # For cancellation
    container_id: Mapped[str | None] = mapped_column(String(255), default=None)  # For cleanup during cancellation
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    total_tests: Mapped[int] = mapped_column(Integer, default=0)
    passed_tests: Mapped[int] = mapped_column(Integer, default=0)
    failed_tests: Mapped[int] = mapped_column(Integer, default=0)
    sub_status: Mapped[str | None] = mapped_column(String(30), default=None)  # Current phase: fetching_pr_info, building_image, running_tests
    ai_review_status: Mapped[str | None] = mapped_column(String(20), default=None)  # null, "running", "completed", "failed"
    ai_summary: Mapped[str | None] = mapped_column(Text, default=None)

    # Relationships
    results = relationship("TestResult", back_populates="test_run", cascade="all, delete-orphan")
    logs = relationship("TestLog", back_populates="test_run", cascade="all, delete-orphan")

    def clone(self) -> "TestRun":
        """Return a new TestRun copying all user-configured settings, resetting runtime state."""
        return TestRun(
            pr_number=self.pr_number,
            branch=self.branch,
            repo=self.repo,
            target_hosts=self.target_hosts,
            target_username=self.target_username,
            target_password=self.target_password,
            protocols=self.protocols,
            kerberos=self.kerberos,
            verbose=self.verbose,
            show_errors=self.show_errors,
            ai_review_enabled=self.ai_review_enabled,
            line_nums=self.line_nums,
            not_tested=self.not_tested,
            dns_server=self.dns_server,
        )

    def __repr__(self):
        return f"<TestRun(id={self.id}, pr_number={self.pr_number}, status={self.status})>"
