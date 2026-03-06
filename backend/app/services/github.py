"""GitHub API integration for fetching PR and branch details."""
import logging
import time
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
NETEXEC_REPO = "Pennyw0rth/NetExec"

# Simple in-memory cache for open PRs list, keyed by repo
pr_cache: dict[str, dict] = {}
PR_CACHE_TTL = 60  # seconds


def get_headers() -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {settings.github_token}",
    }


def get_pr_details(pr_number: int, repo: str | None = None) -> dict:
    """Fetch PR metadata from GitHub API.

    Returns dict with: number, title, head_sha, head_ref, state, user
    """
    repo = repo or NETEXEC_REPO
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
    resp = httpx.get(url, headers=get_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {
        "number": data["number"],
        "title": data["title"],
        "head_sha": data["head"]["sha"],
        "head_ref": data["head"]["ref"],
        "state": data["state"],
        "user": data["user"]["login"],
    }


def get_branch_details(branch: str, repo: str | None = None) -> dict:
    """Fetch branch metadata from GitHub API.

    Returns dict with: name, head_sha
    """
    repo = repo or NETEXEC_REPO
    url = f"{GITHUB_API_BASE}/repos/{repo}/branches/{branch}"
    resp = httpx.get(url, headers=get_headers(), timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return {
        "name": data["name"],
        "head_sha": data["commit"]["sha"],
    }


def validate_pr_exists(pr_number: int, repo: str | None = None) -> bool:
    """Check if a PR number exists in the given repo."""
    try:
        details = get_pr_details(pr_number, repo=repo)
        return details["state"] in ("open", "closed")
    except httpx.HTTPStatusError:
        return False


def fetch_open_prs(repo: str | None = None) -> list[dict]:
    """Fetch open PRs from GitHub, with 60s caching per repo."""
    repo = repo or NETEXEC_REPO
    now = time.time()
    cached = pr_cache.get(repo)
    if cached is not None and (now - cached["fetched_at"]) < PR_CACHE_TTL:
        return cached["data"]

    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls"
    params = {"state": "open", "per_page": 50, "sort": "updated", "direction": "desc"}
    resp = httpx.get(url, headers=get_headers(), params=params, timeout=30)
    resp.raise_for_status()
    prs = [
        {
            "number": pr["number"],
            "title": pr["title"],
            "user": pr["user"]["login"],
            "state": pr["state"],
        }
        for pr in resp.json()
    ]
    pr_cache[repo] = {"data": prs, "fetched_at": now}
    return prs


def get_pr_diff(pr_number: int, repo: str | None = None) -> str:
    """Fetch the diff for a PR from GitHub API."""
    repo = repo or NETEXEC_REPO
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
    headers = get_headers()
    headers["Accept"] = "application/vnd.github.diff"
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def get_pr_body(pr_number: int, repo: str | None = None) -> str:
    """Fetch the PR description/body text."""
    repo = repo or NETEXEC_REPO
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
    resp = httpx.get(url, headers=get_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("body", "") or ""


def search_open_prs(query: str = "") -> list[dict]:
    """Search open PRs by number or title substring."""
    prs = fetch_open_prs()

    if not query:
        return prs

    query_lower = query.lower()
    return [
        pr for pr in prs
        if query_lower in str(pr["number"]) or query_lower in pr["title"].lower()
    ]
