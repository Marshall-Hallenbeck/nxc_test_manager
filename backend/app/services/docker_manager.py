"""Docker container management for test execution."""
import docker
import hashlib
import httpx
import logging
import re
import tempfile
from pathlib import Path
from app.config import settings

logger = logging.getLogger(__name__)

# Regex to strip ANSI escape sequences
ANSI_ESCAPE = re.compile(r'\x1b\[[\x20-\x3f]*[\x40-\x7e]|\x1b\][^\x07]*\x07|\r')
# Strip rich's right-aligned source path (e.g. "          e2e_tests.py:137")
RICH_SOURCE_PATH = re.compile(r'\s{10,}\S+:\d+\s*$')

DOCKER_IMAGE_NAME = "netexec-test-runner"
DOCKERFILE_DIR = str(Path(__file__).resolve().parent.parent.parent / "docker" / "test-runner")
NETEXEC_REPO = "Pennyw0rth/NetExec"

# Cache for poetry.lock hashes to avoid repeated GitHub API calls
_poetry_lock_cache: dict[str, str] = {}


def get_client() -> docker.DockerClient:
    return docker.from_env()


def ensure_image_built() -> None:
    """Build the test runner image if it doesn't exist."""
    client = get_client()
    try:
        client.images.get(DOCKER_IMAGE_NAME)
        logger.info(f"Image {DOCKER_IMAGE_NAME} already exists")
    except docker.errors.ImageNotFound:
        logger.info(f"Building image {DOCKER_IMAGE_NAME} from {DOCKERFILE_DIR}")
        client.images.build(path=DOCKERFILE_DIR, tag=DOCKER_IMAGE_NAME, rm=True)
        logger.info(f"Image {DOCKER_IMAGE_NAME} built successfully")


def get_base_poetry_lock_hash() -> str:
    """Get the hash of poetry.lock from the base image."""
    client = get_client()
    try:
        # Run a quick container to cat the base poetry.lock
        result = client.containers.run(
            DOCKER_IMAGE_NAME,
            command="/poetry.lock.base",
            entrypoint="cat",
            remove=True,
            network_mode="none",
        )
        return hashlib.sha256(result).hexdigest()[:16]
    except Exception as e:
        logger.warning(f"Could not get base poetry.lock hash: {e}")
        return ""


def _repo_hash(repo: str) -> str:
    """Short hash of repo name for image tag namespacing."""
    return hashlib.sha256(repo.encode()).hexdigest()[:8]


def get_poetry_lock_hash(
    pr_number: int | None = None,
    branch: str | None = None,
    repo: str | None = None,
) -> str:
    """Fetch poetry.lock from a PR or branch and return its hash."""
    repo = repo or NETEXEC_REPO
    cache_key = f"{repo}:pr-{pr_number}" if pr_number else f"{repo}:branch-{branch}"

    if cache_key in _poetry_lock_cache:
        return _poetry_lock_cache[cache_key]

    try:
        if pr_number:
            url = f"https://raw.githubusercontent.com/{repo}/refs/pull/{pr_number}/head/poetry.lock"
        else:
            url = f"https://raw.githubusercontent.com/{repo}/refs/heads/{branch}/poetry.lock"
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        if resp.status_code == 200:
            hash_val = hashlib.sha256(resp.content).hexdigest()[:16]
            _poetry_lock_cache[cache_key] = hash_val
            return hash_val
    except Exception as e:
        label = f"PR #{pr_number}" if pr_number else f"branch '{branch}'"
        logger.warning(f"Could not fetch poetry.lock for {label} in {repo}: {e}")

    return ""


def get_source_image_name(
    pr_number: int | None = None,
    branch: str | None = None,
    repo: str | None = None,
) -> str:
    """Get the image name for a specific PR or branch."""
    repo = repo or NETEXEC_REPO
    rh = _repo_hash(repo)
    if pr_number:
        return f"{DOCKER_IMAGE_NAME}:{rh}-pr-{pr_number}"
    return f"{DOCKER_IMAGE_NAME}:{rh}-branch-{branch}"


def source_image_exists(
    pr_number: int | None = None,
    branch: str | None = None,
    repo: str | None = None,
) -> bool:
    """Check if a source-specific image exists."""
    client = get_client()
    try:
        client.images.get(get_source_image_name(pr_number, branch, repo))
        return True
    except docker.errors.ImageNotFound:
        return False


def build_source_image(
    pr_number: int | None = None,
    branch: str | None = None,
    repo: str | None = None,
    log_callback=None,
) -> bool:
    """Build a source-specific image with updated dependencies."""
    client = get_client()
    repo = repo or NETEXEC_REPO
    image_tag = get_source_image_name(pr_number, branch, repo)
    label = f"PR #{pr_number}" if pr_number else f"branch '{branch}'"

    if log_callback:
        log_callback(f"Building image for {label} with updated dependencies...")

    if pr_number:
        fetch_cmd = (
            f"git fetch --depth 1 origin pull/{pr_number}/head:pr-{pr_number} && "
            f"git checkout -q pr-{pr_number}"
        )
    else:
        fetch_cmd = (
            f"git fetch --depth 1 origin {branch} && "
            f"git checkout -q FETCH_HEAD"
        )

    dockerfile_content = f"""
FROM {DOCKER_IMAGE_NAME}:latest

WORKDIR /netexec

# Fetch and checkout the source
RUN git init -q && \\
    git remote add origin https://github.com/{repo}.git && \\
    {fetch_cmd}

# Install updated dependencies
# Poetry has a bug where git deps pinned to HEAD can be silently removed during
# the update phase but not reinstalled (stale metadata check reports "Already installed").
# Workaround: extract git deps from pyproject.toml and force-reinstall them with pip.
RUN poetry config virtualenvs.create false && \\
    poetry install --no-interaction; \\
    grep -oP 'git\\+https://[^"]+' pyproject.toml | xargs -r pip install --force-reinstall --no-deps

# Verify critical dependencies are installed
RUN python -c "from nxc.connection import connection; print('Dependency check passed')"

# Save poetry.lock as the new base for this image
RUN cp poetry.lock /poetry.lock.base
"""

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = Path(tmpdir) / "Dockerfile"
            dockerfile_path.write_text(dockerfile_content)

            logger.info(f"Building source-specific image: {image_tag}")
            image, build_logs = client.images.build(
                path=tmpdir,
                tag=image_tag,
                rm=True,
                pull=False,
                network_mode="host",
            )

            if log_callback:
                for log in build_logs:
                    if "stream" in log:
                        line = log["stream"].strip()
                        if line:
                            log_callback(line)

            logger.info(f"Successfully built {image_tag}")
            return True

    except Exception as e:
        logger.error(f"Failed to build source image: {e}")
        if log_callback:
            log_callback(f"Failed to build image: {e}")
        return False


def get_image(
    pr_number: int | None = None,
    branch: str | None = None,
    repo: str | None = None,
    log_callback=None,
) -> str:
    """Get the appropriate image for a PR or branch, building if needed.

    Returns the image name to use.
    """
    ensure_image_built()
    repo = repo or NETEXEC_REPO
    label = f"PR #{pr_number}" if pr_number else f"branch '{branch}'"

    # For branch runs, always rebuild (branch HEAD may have changed)
    # For PR runs, check cache
    if pr_number and source_image_exists(pr_number=pr_number, repo=repo):
        logger.info(f"Using existing image for {label} in {repo}")
        if log_callback:
            log_callback(f"Using cached image for {label}")
        return get_source_image_name(pr_number=pr_number, repo=repo)

    # Compare poetry.lock hashes
    base_hash = get_base_poetry_lock_hash()
    source_hash = get_poetry_lock_hash(pr_number=pr_number, branch=branch, repo=repo)

    if not source_hash:
        logger.warning(f"Could not fetch poetry.lock for {label}, using base image")
        return DOCKER_IMAGE_NAME

    if base_hash == source_hash:
        logger.info(f"Dependencies unchanged for {label}, using base image")
        if log_callback:
            log_callback("Dependencies unchanged - using cached base image")
        return DOCKER_IMAGE_NAME

    # Dependencies changed, build source-specific image
    logger.info(f"Dependencies changed for {label}, building image")
    if build_source_image(pr_number=pr_number, branch=branch, repo=repo, log_callback=log_callback):
        return get_source_image_name(pr_number=pr_number, branch=branch, repo=repo)
    else:
        raise RuntimeError(f"Failed to build image for {label}. Dependencies could not be installed.")


def run_test_container(
    pr_number: int | None,
    target_host: str,
    target_username: str,
    target_password: str,
    branch: str | None = None,
    repo: str | None = None,
    protocols: str | None = None,
    kerberos: bool = False,
    verbose: bool = False,
    show_errors: bool = False,
    line_nums: str | None = None,
    not_tested: bool = False,
    dns_server: str | None = None,
    log_callback=None,
    image_name: str | None = None,
) -> tuple[int, str]:
    """Run an ephemeral test container and stream output.

    Args:
        pr_number: GitHub PR number to test (None for branch runs)
        target_host: Target IP/hostname
        target_username: Auth username
        target_password: Auth password
        branch: Branch name to test (None for PR runs)
        repo: Repository in owner/name format (None for default)
        protocols: Comma-separated protocols to test (empty = all)
        kerberos: Use Kerberos authentication
        verbose: Display full command output
        show_errors: Display errors from commands
        line_nums: Comma-separated line numbers/ranges to run (e.g. "5,10-15,20")
        not_tested: Display commands that didn't get tested
        dns_server: DNS server IP/hostname for Kerberos/domain environments
        log_callback: Optional callable(line: str) to stream logs
        image_name: Docker image to use (if None, resolves automatically)

    Returns:
        (exit_code, container_id)
    """
    client = get_client()
    repo = repo or NETEXEC_REPO
    label = f"PR #{pr_number}" if pr_number else f"branch '{branch}'"

    # Use provided image or resolve it
    if not image_name:
        image_name = get_image(pr_number=pr_number, branch=branch, repo=repo, log_callback=log_callback)

    env = {
        "PR_NUMBER": str(pr_number) if pr_number else "",
        "BRANCH": branch or "",
        "REPO": repo,
        "REPO_URL": f"https://github.com/{repo}.git",
        "TARGET_HOST": target_host,
        "TARGET_USERNAME": target_username,
        "TARGET_PASSWORD": target_password,
        "PROTOCOLS": protocols or "",
        "USE_KERBEROS": "1" if kerberos else "",
        "VERBOSE": "1" if verbose else "",
        "SHOW_ERRORS": "1" if show_errors else "",
        "LINE_NUMS": line_nums or "",
        "NOT_TESTED": "1" if not_tested else "",
        "DNS_SERVER": dns_server or "",
        "CONTAINER_TIMEOUT": str(settings.container_timeout),
        # Neo4j / BloodHound connection details
        "NEO4J_URI": "127.0.0.1",
        "NEO4J_PORT": "7687",
        "NEO4J_USER": "neo4j",
        "NEO4J_PASS": "bloodhound123",
        # Empire connection details
        "EMPIRE_HOST": "127.0.0.1",
        "EMPIRE_PORT": "1337",
        # Disable rich library's path display and ensure proper output
        "PYTHONUNBUFFERED": "1",
        "COLUMNS": "300",
        "LINES": "50",
        # Tell rich to use a real terminal width and hide source paths
        "TERM": "xterm-256color",
    }

    container = client.containers.run(
        image_name,
        environment=env,
        network_mode="host",
        mem_limit=settings.container_memory_limit,
        detach=True,
        remove=False,  # We remove manually after collecting logs
    )

    container_id = container.id
    logger.info(f"Started container {container_id[:12]} for {label} using {image_name}")

    # Stream logs - buffer chunks and split on actual newlines
    try:
        buffer = ""
        for chunk in container.logs(stream=True, follow=True):
            # Decode and strip ANSI escape sequences
            text = chunk.decode("utf-8", errors="replace")
            text = text.replace("\x00", "")
            text = ANSI_ESCAPE.sub("", text)
            buffer += text
            # Process complete lines from buffer
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = ANSI_ESCAPE.sub("", line)
                line = RICH_SOURCE_PATH.sub("", line)  # Strip rich source paths
                line = line.strip()
                if log_callback and line:
                    log_callback(line)
        # Flush any remaining content
        if buffer.strip() and log_callback:
            log_callback(buffer.strip())
    except Exception as e:
        logger.error(f"Error streaming logs: {e}")

    # Wait for completion
    result = container.wait(timeout=settings.container_timeout)
    exit_code = result.get("StatusCode", -1)

    # Cleanup
    try:
        container.remove(force=True)
        logger.info(f"Removed container {container_id[:12]}")
    except Exception as e:
        logger.warning(f"Failed to remove container {container_id[:12]}: {e}")

    return exit_code, container_id


def stop_container(container_id: str) -> bool:
    """Stop and remove a running container. Returns True if successful."""
    client = get_client()
    try:
        container = client.containers.get(container_id)
        container.stop(timeout=10)
        container.remove(force=True)
        logger.info(f"Stopped and removed container {container_id[:12]}")
        return True
    except docker.errors.NotFound:
        logger.warning(f"Container {container_id[:12]} not found")
        return False
    except Exception as e:
        logger.error(f"Error stopping container {container_id[:12]}: {e}")
        return False


def cleanup_pr_images(keep_recent: int = 10) -> int:
    """Remove old PR-specific images, keeping the most recent ones.

    Returns the number of images removed.
    """
    client = get_client()
    removed = 0

    try:
        # List all source-specific images (PR and branch)
        images = client.images.list(name=DOCKER_IMAGE_NAME)
        source_images = []

        for img in images:
            for tag in img.tags:
                if ":" in tag and tag != f"{DOCKER_IMAGE_NAME}:latest":
                    source_images.append((img, tag))

        # Sort by creation date (newest first) and remove old ones
        source_images.sort(key=lambda x: x[0].attrs.get("Created", ""), reverse=True)

        for _img, tag in source_images[keep_recent:]:
            try:
                client.images.remove(tag, force=True)
                logger.info(f"Removed old image: {tag}")
                removed += 1
            except Exception as e:
                logger.warning(f"Could not remove {tag}: {e}")

    except Exception as e:
        logger.error(f"Error during image cleanup: {e}")

    return removed
