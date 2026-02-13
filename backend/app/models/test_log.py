"""TestLog database model."""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class TestLog(Base):
    """Test log model for real-time streaming."""

    __tablename__ = "test_logs"

    id = Column(Integer, primary_key=True, index=True)
    test_run_id = Column(Integer, ForeignKey("test_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    log_line = Column(Text, nullable=False)
    level = Column(String(20), default="INFO")  # INFO, WARNING, ERROR, DEBUG

    # Relationships
    test_run = relationship("TestRun", back_populates="logs")

    def __repr__(self):
        return f"<TestLog(id={self.id}, test_run_id={self.test_run_id}, level={self.level})>"
