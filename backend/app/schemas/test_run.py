"""Pydantic schemas for test runs."""
import re
from pydantic import BaseModel, ConfigDict, model_validator
from datetime import datetime


class TestRunCreate(BaseModel):
    pr_number: int | None = None
    branch: str | None = None
    repo: str | None = None
    target_hosts: str | None = None
    target_username: str | None = None
    target_password: str | None = None
    # e2e_tests.py options
    protocols: list[str] | None = None  # e.g. ["smb", "ldap"]
    kerberos: bool = False
    verbose: bool = False
    show_errors: bool = False
    ai_review: bool = False
    line_nums: str | None = None  # Comma-separated line numbers/ranges e.g. "5,10-15,20"
    not_tested: bool = False  # Display commands that didn't get tested
    dns_server: str | None = None  # DNS server IP/hostname

    @model_validator(mode="after")
    def validate_source(self):
        if self.pr_number is not None and self.branch is not None:
            raise ValueError("Specify either pr_number or branch, not both")
        if self.pr_number is None and self.branch is None:
            raise ValueError("Either pr_number or branch is required")
        if self.branch is not None and not re.match(r"^[A-Za-z0-9/_.\-]+$", self.branch):
            raise ValueError("branch contains invalid characters")
        if self.repo is not None and not re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", self.repo):
            raise ValueError("repo must be in 'owner/name' format")
        return self


class TestResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    test_name: str
    target_host: str | None
    status: str
    duration: float | None
    output: str | None
    error_message: str | None


class TestLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: datetime
    log_line: str
    level: str


class TestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pr_number: int | None
    branch: str | None = None
    repo: str | None = None
    pr_title: str | None
    commit_sha: str | None
    target_hosts: str
    target_username: str | None
    target_password: str | None
    protocols: str | None
    kerberos: bool
    verbose: bool
    show_errors: bool
    ai_review_enabled: bool
    line_nums: str | None
    not_tested: bool
    dns_server: str | None
    status: str
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    total_tests: int
    passed_tests: int
    failed_tests: int
    ai_review_status: str | None = None
    ai_summary: str | None = None


class TestRunDetail(TestRunOut):
    results: list[TestResultOut] = []


class TestRunListOut(BaseModel):
    items: list[TestRunOut]
    total: int
    page: int
    per_page: int


class CompareOut(BaseModel):
    run1: TestRunDetail
    run2: TestRunDetail
