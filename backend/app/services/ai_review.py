"""AI review service using Claude CLI."""
import glob
import json
import logging
import os
import shutil
import subprocess

from app.services import github

logger = logging.getLogger(__name__)

MAX_DIFF_CHARS = 80000
MAX_OUTPUT_PER_TEST = 3000

# Set by check_claude_available() at startup
CLAUDE_AVAILABLE = False
CLAUDE_UNAVAILABLE_REASON = ""


def find_claude_cli() -> str:
    """Find the claude CLI binary, checking PATH and Docker mount location."""
    # Check PATH first (host development)
    found = shutil.which("claude")
    if found:
        return found

    # Check Docker-mounted location (latest version)
    mounted = sorted(glob.glob("/opt/claude/versions/*"))
    if mounted:
        return mounted[-1]

    return "claude"


CLAUDE_CLI = find_claude_cli()


def build_env() -> dict:
    """Build a clean environment for Claude CLI subprocesses."""
    env = os.environ.copy()
    # Ensure HOME is set for Docker containers where .claude is mounted to /root
    if os.path.exists("/root/.claude"):
        env["HOME"] = "/root"
    # Remove CLAUDECODE to avoid "nested session" detection when the backend
    # is launched from within a Claude Code terminal
    env.pop("CLAUDECODE", None)
    return env


def check_claude_available() -> None:
    """Probe Claude CLI auth status at startup. Sets CLAUDE_AVAILABLE and CLAUDE_UNAVAILABLE_REASON."""
    global CLAUDE_AVAILABLE, CLAUDE_UNAVAILABLE_REASON

    env = build_env()

    try:
        result = subprocess.run(
            [CLAUDE_CLI, "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
            env=env,
        )
    except FileNotFoundError:
        CLAUDE_AVAILABLE = False
        CLAUDE_UNAVAILABLE_REASON = "Claude CLI not installed"
        logger.warning("Claude CLI not found — AI review disabled")
        return
    except subprocess.TimeoutExpired:
        CLAUDE_AVAILABLE = False
        CLAUDE_UNAVAILABLE_REASON = "Claude CLI timed out during auth check"
        logger.warning("Claude CLI auth check timed out — AI review disabled")
        return

    if result.returncode != 0:
        CLAUDE_AVAILABLE = False
        CLAUDE_UNAVAILABLE_REASON = f"Claude CLI error (exit {result.returncode})"
        logger.warning(f"Claude CLI auth check failed (exit {result.returncode}) — AI review disabled")
        return

    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        CLAUDE_AVAILABLE = False
        CLAUDE_UNAVAILABLE_REASON = "Claude CLI returned invalid JSON"
        logger.warning("Claude CLI auth check returned invalid JSON — AI review disabled")
        return

    if data.get("loggedIn"):
        CLAUDE_AVAILABLE = True
        CLAUDE_UNAVAILABLE_REASON = ""
        logger.info("Claude CLI authenticated — AI review enabled")
    else:
        CLAUDE_AVAILABLE = False
        CLAUDE_UNAVAILABLE_REASON = "Claude CLI not authenticated"
        logger.warning("Claude CLI not authenticated — AI review disabled")


def build_prompt(
    pr_number: int,
    pr_title: str | None,
    pr_body: str,
    diff: str,
    results: list[dict],
    summary: dict,
) -> str:
    """Build the prompt for Claude to review."""
    # Truncate diff if too large
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS] + f"\n\n... [diff truncated, {len(diff) - MAX_DIFF_CHARS} chars omitted]"

    # Format test results
    results_text = ""
    for r in results:
        status_icon = {"passed": "PASS", "failed": "FAIL", "skipped": "SKIP", "error": "ERROR"}.get(r["status"], r["status"])
        results_text += f"\n[{status_icon}] {r['test_name']}"
        if r.get("target_host"):
            results_text += f" (target: {r['target_host']})"
        if r.get("duration") is not None:
            results_text += f" [{r['duration']:.1f}s]"
        if r["status"] in ("failed", "error"):
            if r.get("error_message"):
                results_text += f"\n  Error: {r['error_message']}"
            if r.get("output"):
                output = r["output"][:MAX_OUTPUT_PER_TEST]
                if len(r["output"]) > MAX_OUTPUT_PER_TEST:
                    output += "\n  ... [output truncated]"
                results_text += f"\n  Output:\n{output}"

    prompt = f"""You are reviewing a pull request for NetExec (a network execution tool used for penetration testing) and its end-to-end test results.

## PR #{pr_number}: {pr_title or 'No title'}

### PR Description
{pr_body or 'No description provided.'}

### PR Diff
```diff
{diff}
```

### Test Results Summary
- Total: {summary.get('total', 0)}
- Passed: {summary.get('passed', 0)}
- Failed: {summary.get('failed', 0)}

### Individual Test Results
{results_text or 'No test results available.'}

---

Please provide a concise review covering:
1. **PR Summary**: What does this PR change? (2-3 sentences)
2. **Test Analysis**: Analyze the test results. If there are failures, are they related to the PR changes or pre-existing issues?
3. **Risk Assessment**: Any concerns about the changes? (security, compatibility, edge cases)
4. **AI-Generated Code Assessment**: Analyze the diff for signs of AI-generated code (e.g. overly verbose comments, boilerplate patterns, unnatural naming, excessive docstrings, hallucinated imports, generic error handling, suspiciously uniform style). State your conclusion (likely AI-generated, likely human-written, or mixed/uncertain) and explain the specific signals that led to it.
5. **Verdict**: Overall assessment — does this PR look safe to merge based on the test results?

Keep the review concise and actionable. Use markdown formatting."""

    return prompt


def generate_review(
    pr_number: int,
    pr_title: str | None,
    results: list[dict],
    summary: dict,
) -> str:
    """Generate an AI review of the PR and test results using the Claude CLI.

    Raises RuntimeError if the CLI is not available or fails.
    """
    # Fetch PR diff from GitHub — abort review if unavailable
    try:
        diff = github.get_pr_diff(pr_number)
    except Exception as e:
        raise RuntimeError(f"Cannot generate review without PR diff: {e}")

    if not diff or not diff.strip():
        raise RuntimeError("Cannot generate review: PR diff is empty")

    pr_body = github.get_pr_body(pr_number)

    prompt = build_prompt(pr_number, pr_title, pr_body, diff, results, summary)

    # Call claude CLI
    env = build_env()
    try:
        result = subprocess.run(
            [CLAUDE_CLI, "-p", "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
            env=env,
        )
    except FileNotFoundError:
        raise RuntimeError("Claude CLI not found. Install Claude Code: https://claude.ai/code")
    except subprocess.TimeoutExpired:
        raise RuntimeError("Claude CLI timed out after 120 seconds")

    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"Claude CLI failed (exit {result.returncode}): {stderr}")

    summary_text = result.stdout.strip()
    if not summary_text:
        raise RuntimeError("Claude CLI returned empty output")

    return summary_text
