"""Test execution orchestration."""
import ipaddress
import logging
import re
from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.config import settings
from app.models.test_run import TestRun, TestRunStatus
from app.models.test_result import TestResult, TestStatus
from app.models.test_log import TestLog
from . import docker_manager, github

logger = logging.getLogger(__name__)


def parse_target_hosts(target_hosts_str: str) -> list[str]:
    """Parse target hosts string into list of individual IPs.

    Supports: single IP, comma-separated IPs, CIDR subnets, or mixed.
    """
    hosts = []
    for part in target_hosts_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            # CIDR subnet - expand to individual IPs (skip network/broadcast)
            try:
                network = ipaddress.ip_network(part, strict=False)
                hosts.extend(str(ip) for ip in network.hosts())
            except ValueError:
                logger.warning(f"Invalid CIDR notation: {part}")
        else:
            hosts.append(part)
    return hosts


def parse_test_output(output: str) -> dict:
    """Parse test output to extract test results.

    Supports NetExec e2e_tests.py format which uses:
    - Individual test lines ending with checkmark or X mark
    - Summary line: "Ran X tests in Y - Passed: N Failed: M Not Tested: O"

    Returns dict with 'results' list (each with 'output' snippet) and 'summary' counts.
    """
    results = []
    pass_markers = {"\u2705", "\u2714", "\u2713"}  # U+2705, U+2714, U+2713
    fail_markers = {"\u274c"}              # U+274C
    all_markers = pass_markers | fail_markers

    # Split output into per-test sections at "Running command:" boundaries.
    # Each section contains one test's full output.
    lines = output.split("\n")
    sections: list[tuple[int, int]] = []  # (start_line, end_line) indices
    for i, line in enumerate(lines):
        if "Running command:" in line:
            sections.append((i, -1))
            if len(sections) > 1:
                sections[-2] = (sections[-2][0], i)
    if sections:
        sections[-1] = (sections[-1][0], len(lines))

    # Build a lookup: for each line index that has a marker, find its section text
    def section_for_line(line_idx: int) -> str:
        for start, end in sections:
            if start <= line_idx < end:
                return "\n".join(lines[start:end]).strip()
        return ""

    # Try NetExec format - look for lines with pass/fail markers
    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        has_pass = any(m in line for m in pass_markers)
        has_fail = any(m in line for m in fail_markers)
        if has_pass or has_fail:
            cmd = line
            for m in all_markers:
                cmd = cmd.replace(m, "")
            if "\u2514\u2500$" in cmd:
                cmd = cmd.split("\u2514\u2500$", 1)[1]
            cmd = cmd.strip()
            if len(cmd) > 100:
                cmd = cmd[:97] + "..."
            results.append({
                "test_name": cmd,
                "status": TestStatus.PASSED if has_pass else TestStatus.FAILED,
                "duration": None,
                "output": section_for_line(i),
            })

    # Also parse the summary line for aggregate counts
    summary = {"passed": 0, "failed": 0, "not_tested": 0, "total": 0}
    summary_pattern = re.compile(
        r"Ran\s+(\d+)\s+tests?\s+.*?Passed:\s*(\d+).*?Failed:\s*(\d+)(?:.*?Not Tested:\s*(\d+))?",
        re.IGNORECASE | re.DOTALL
    )
    match = summary_pattern.search(output)
    if match:
        summary["total"] = int(match.group(1))
        summary["passed"] = int(match.group(2))
        summary["failed"] = int(match.group(3))
        summary["not_tested"] = int(match.group(4)) if match.group(4) else 0

    # If no emoji-based results but we have a summary, use summary counts
    if not results and summary["total"] > 0:
        pass

    # Fallback: try pytest-style output
    if not results and summary["total"] == 0:
        pattern = re.compile(r"^(PASSED|FAILED|ERROR|SKIPPED)\s+(.+?)(?:\s+in\s+([\d.]+)s)?$", re.MULTILINE)
        matches = pattern.findall(output)
        for status_str, name, duration_str in matches:
            status_map = {
                "PASSED": TestStatus.PASSED,
                "FAILED": TestStatus.FAILED,
                "ERROR": TestStatus.ERROR,
                "SKIPPED": TestStatus.SKIPPED,
            }
            results.append({
                "test_name": name.strip(),
                "status": status_map.get(status_str, TestStatus.ERROR),
                "duration": float(duration_str) if duration_str else None,
                "output": None,
            })

    return {"results": results, "summary": summary}


def run_test(db: Session, test_run_id: int, target_password: str) -> None:
    """Execute a full test run.

    Args:
        db: Database session
        test_run_id: ID of the TestRun record
        target_password: Password (not stored in DB, passed at runtime)
    """
    test_run = db.get(TestRun, test_run_id)
    if not test_run:
        logger.error(f"TestRun {test_run_id} not found")
        return

    # Mark as running
    test_run.status = TestRunStatus.RUNNING
    test_run.sub_status = "fetching_pr_info"
    test_run.started_at = datetime.now(UTC)
    db.commit()

    # Determine effective repo
    repo = test_run.repo or settings.default_repo

    try:
        if test_run.pr_number:
            # PR mode: fetch PR details
            pr_info = github.get_pr_details(test_run.pr_number, repo=repo)
            test_run.pr_title = pr_info["title"]
            test_run.commit_sha = pr_info["head_sha"]
        else:
            # Branch mode: fetch branch details
            branch_info = github.get_branch_details(test_run.branch, repo=repo)
            test_run.pr_title = f"{test_run.branch} @ {repo}"
            test_run.commit_sha = branch_info["head_sha"]
        db.commit()
    except Exception as e:
        label = f"PR #{test_run.pr_number}" if test_run.pr_number else f"branch '{test_run.branch}'"
        logger.error(f"Failed to fetch details for {label} in {repo}: {e}")
        add_log(db, test_run_id, f"FATAL: Could not fetch details from GitHub API: {e}", "ERROR")
        test_run.status = TestRunStatus.FAILED
        test_run.sub_status = None
        test_run.completed_at = datetime.now(UTC)
        db.commit()
        return

    target_hosts = parse_target_hosts(test_run.target_hosts)
    username = test_run.target_username or settings.default_target_username
    password = target_password or settings.default_target_password

    # Resolve the Docker image before running any tests — if the image build
    # fails (e.g. dependencies can't be installed), abort the entire run.
    test_run.sub_status = "building_image"
    db.commit()

    def log(line: str):
        add_log(db, test_run_id, line)

    label = f"PR #{test_run.pr_number}" if test_run.pr_number else f"branch '{test_run.branch}'"

    try:
        image_name = docker_manager.get_image(
            pr_number=test_run.pr_number,
            branch=test_run.branch,
            repo=repo,
            log_callback=log,
        )
    except Exception as e:
        logger.error(f"Failed to prepare Docker image for {label}: {e}")
        add_log(db, test_run_id, f"FATAL: {e}", "ERROR")
        test_run.status = TestRunStatus.FAILED
        test_run.sub_status = None
        test_run.completed_at = datetime.now(UTC)
        db.commit()
        return

    test_run.sub_status = "running_tests"
    db.commit()

    all_output = []
    total_passed = 0
    total_failed = 0
    total_tests = 0

    for host in target_hosts:
        # Check for cancellation
        db.refresh(test_run)
        if test_run.status == TestRunStatus.CANCELLED:
            add_log(db, test_run_id, "Test cancelled by user", "WARNING")
            return

        add_log(db, test_run_id, f"=== Testing against {host} ===")
        output_lines = []

        def log_callback(line: str, _lines=output_lines):
            _lines.append(line)
            add_log(db, test_run_id, line)

        try:
            exit_code, container_id = docker_manager.run_test_container(
                pr_number=test_run.pr_number,
                target_host=host,
                target_username=username,
                target_password=password,
                branch=test_run.branch,
                repo=repo,
                protocols=test_run.protocols,
                kerberos=bool(test_run.kerberos),
                verbose=bool(test_run.verbose),
                show_errors=bool(test_run.show_errors),
                line_nums=test_run.line_nums,
                not_tested=bool(test_run.not_tested),
                dns_server=test_run.dns_server,
                image_name=image_name,
                log_callback=log_callback,
            )
            test_run.container_id = container_id
            db.commit()

            output_text = "\n".join(output_lines)
            all_output.append(output_text)

            # Parse results
            parsed = parse_test_output(output_text)
            individual_results = parsed["results"]
            summary = parsed["summary"]

            if individual_results:
                # Store individual test results with per-test output
                for r in individual_results:
                    result = TestResult(
                        test_run_id=test_run_id,
                        test_name=r["test_name"],
                        target_host=host,
                        status=r["status"],
                        duration=r.get("duration"),
                        output=r.get("output") or output_text,
                    )
                    db.add(result)
                    if r["status"] == TestStatus.PASSED:
                        total_passed += 1
                    else:
                        total_failed += 1
                    total_tests += 1
            elif summary["total"] > 0:
                # Use summary counts if no individual results but summary exists
                total_tests += summary["total"]
                total_passed += summary["passed"]
                total_failed += summary["failed"]
                # Store a single result entry with the summary
                status = TestStatus.PASSED if summary["failed"] == 0 else TestStatus.FAILED
                result = TestResult(
                    test_run_id=test_run_id,
                    test_name=f"e2e_tests @ {host} ({summary['passed']}/{summary['total']} passed)",
                    target_host=host,
                    status=status,
                    output=output_text,
                )
                db.add(result)
            else:
                # No results parsed at all - use exit code as fallback
                status = TestStatus.PASSED if exit_code == 0 else TestStatus.FAILED
                result = TestResult(
                    test_run_id=test_run_id,
                    test_name=f"e2e_tests @ {host}",
                    target_host=host,
                    status=status,
                    output=output_text,
                )
                db.add(result)
                total_tests += 1
                if exit_code == 0:
                    total_passed += 1
                else:
                    total_failed += 1

            db.commit()

        except Exception as e:
            logger.error(f"Error testing against {host}: {e}")
            db.rollback()
            add_log(db, test_run_id, f"Error testing against {host}: {e}", "ERROR")
            total_failed += 1
            total_tests += 1

    # Finalize
    test_run.total_tests = total_tests
    test_run.passed_tests = total_passed
    test_run.failed_tests = total_failed
    test_run.status = TestRunStatus.COMPLETED if total_failed == 0 else TestRunStatus.FAILED
    test_run.sub_status = None
    test_run.completed_at = datetime.now(UTC)
    db.commit()

    add_log(db, test_run_id, f"=== Completed: {total_passed}/{total_tests} passed ===")


def add_log(db: Session, test_run_id: int, line: str, level: str = "INFO") -> None:
    log = TestLog(test_run_id=test_run_id, log_line=line.replace("\x00", ""), level=level)
    db.add(log)
    db.commit()
