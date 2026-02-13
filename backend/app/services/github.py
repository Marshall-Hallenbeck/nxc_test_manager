"""GitHub API integration for fetching PR details."""
import logging
import time
import httpx
from app.config import settings


logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
NETEXEC_REPO = "Pennyw0rth/NetExec"

# Simple in-memory cache for open PRs list
_pr_cache: dict = {"data": None, "fetched_at": 0}
_PR_CACHE_TTL = 60  # seconds


def _get_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    return headers


def get_pr_details(pr_number: int) -> dict:
    """Fetch PR metadata from GitHub API.

    Returns dict with: number, title, head_sha, head_ref, state, user
    """
    url = f"{GITHUB_API_BASE}/repos/{NETEXEC_REPO}/pulls/{pr_number}"
    resp = httpx.get(url, headers=_get_headers(), timeout=30)
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


def validate_pr_exists(pr_number: int) -> bool:
    """Check if a PR number exists in the NetExec repo."""
    try:
        details = get_pr_details(pr_number)
        return details["state"] in ("open", "closed")
    except httpx.HTTPStatusError:
        return False


def _fetch_open_prs() -> list[dict]:
    """Fetch open PRs from GitHub, with 60s caching."""
    now = time.time()
    if _pr_cache["data"] is not None and (now - _pr_cache["fetched_at"]) < _PR_CACHE_TTL:
        return _pr_cache["data"]

    url = f"{GITHUB_API_BASE}/repos/{NETEXEC_REPO}/pulls"
    params = {"state": "open", "per_page": 50, "sort": "updated", "direction": "desc"}
    resp = httpx.get(url, headers=_get_headers(), params=params, timeout=30)
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
    _pr_cache["data"] = prs
    _pr_cache["fetched_at"] = now
    return prs


def get_pr_diff(pr_number: int) -> str:
    """Fetch the diff for a PR from GitHub API."""
    url = f"{GITHUB_API_BASE}/repos/{NETEXEC_REPO}/pulls/{pr_number}"
    headers = _get_headers()
    headers["Accept"] = "application/vnd.github.diff"
    resp = httpx.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def get_pr_body(pr_number: int) -> str:
    """Fetch the PR description/body text."""
    url = f"{GITHUB_API_BASE}/repos/{NETEXEC_REPO}/pulls/{pr_number}"
    resp = httpx.get(url, headers=_get_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("body", "") or ""


def search_open_prs(query: str = "") -> list[dict]:
    """Search open PRs by number or title substring."""
    try:
        prs = _fetch_open_prs()
    except Exception as e:
        logger.warning(f"Failed to fetch open PRs: {e}")
        return []

    if not query:
        return prs

    query_lower = query.lower()
    return [
        pr for pr in prs
        if query_lower in str(pr["number"]) or query_lower in pr["title"].lower()
    ]
