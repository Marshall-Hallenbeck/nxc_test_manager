"""TestResult database model."""
from sqlalchemy import Column, Integer, String, Float, Text, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum
from app.database import Base


class TestStatus(enum.StrEnum):
    """Test status enum."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class TestResult(Base):
    """Test result model."""

    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, index=True)
    test_run_id = Column(Integer, ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    test_name = Column(String(500), nullable=False)
    target_host = Column(String(100))  # Specific IP tested (for multi-target runs)
    status = Column(Enum(TestStatus), nullable=False)
    duration = Column(Float)  # Duration in seconds
    output = Column(Text)  # Test output
    error_message = Column(Text)  # Error message if failed

    # Relationships
    test_run = relationship("TestRun", back_populates="results")

    def __repr__(self):
        return f"<TestResult(id={self.id}, test_name={self.test_name}, status={self.status})>"
