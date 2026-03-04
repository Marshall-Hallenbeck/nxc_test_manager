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

# Cache for poetry.lock hashes to avoid repeated GitHub API calls
_poetry_lock_cache: dict[int, str] = {}


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
            command="cat /poetry.lock.base",
            remove=True,
            network_mode="none",
        )
        return hashlib.sha256(result).hexdigest()[:16]
    except Exception as e:
        logger.warning(f"Could not get base poetry.lock hash: {e}")
        return ""


def get_pr_poetry_lock_hash(pr_number: int) -> str:
    """Fetch poetry.lock from a PR and return its hash."""
    if pr_number in _poetry_lock_cache:
        return _poetry_lock_cache[pr_number]

    try:
        # Fetch poetry.lock from the PR's head commit
        url = f"https://raw.githubusercontent.com/Pennyw0rth/NetExec/refs/pull/{pr_number}/head/poetry.lock"
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        if resp.status_code == 200:
            hash_val = hashlib.sha256(resp.content).hexdigest()[:16]
            _poetry_lock_cache[pr_number] = hash_val
            return hash_val
    except Exception as e:
        logger.warning(f"Could not fetch poetry.lock for PR #{pr_number}: {e}")

    return ""


def get_pr_image_name(pr_number: int) -> str:
    """Get the image name for a specific PR."""
    return f"{DOCKER_IMAGE_NAME}:pr-{pr_number}"


def pr_image_exists(pr_number: int) -> bool:
    """Check if a PR-specific image exists."""
    client = get_client()
    try:
        client.images.get(get_pr_image_name(pr_number))
        return True
    except docker.errors.ImageNotFound:
        return False


def build_pr_image(pr_number: int, log_callback=None) -> bool:
    """Build a PR-specific image with updated dependencies."""
    client = get_client()
    pr_image = get_pr_image_name(pr_number)

    if log_callback:
        log_callback(f"Building PR-specific image for updated dependencies...")

    # Create a temporary Dockerfile that installs deps for this PR
    dockerfile_content = f"""
FROM {DOCKER_IMAGE_NAME}:latest

WORKDIR /netexec

# Fetch and checkout the PR
RUN git init -q && \\
    git remote add origin https://github.com/Pennyw0rth/NetExec.git && \\
    git fetch --depth 1 origin pull/{pr_number}/head:pr-{pr_number} && \\
    git checkout -q pr-{pr_number}

# Install updated dependencies
# Poetry has a bug where git deps pinned to HEAD can be silently removed during
# the update phase but not reinstalled (stale metadata check reports "Already installed").
# Workaround: extract git deps from pyproject.toml and force-reinstall them with pip.
RUN poetry config virtualenvs.create false && \\
    poetry install --no-interaction; \\
    grep -oP 'git\\+https://[^"]+' pyproject.toml | xargs -r pip install --force-reinstall --no-deps

# Verify critical dependencies are installed
RUN python -c "from nxc.connection import connection; print('Dependency check passed')"

# Save PR's poetry.lock as the new base for this image
RUN cp poetry.lock /poetry.lock.base
"""

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            dockerfile_path = Path(tmpdir) / "Dockerfile"
            dockerfile_path.write_text(dockerfile_content)

            # Build the image
            logger.info(f"Building PR-specific image: {pr_image}")
            image, build_logs = client.images.build(
                path=tmpdir,
                tag=pr_image,
                rm=True,
                pull=False,
                network_mode="host",
            )

            # Log build output if callback provided
            if log_callback:
                for log in build_logs:
                    if "stream" in log:
                        line = log["stream"].strip()
                        if line:
                            log_callback(line)

            logger.info(f"Successfully built {pr_image}")
            return True

    except Exception as e:
        logger.error(f"Failed to build PR image: {e}")
        if log_callback:
            log_callback(f"Failed to build PR-specific image: {e}")
        return False


def get_image_for_pr(pr_number: int, log_callback=None) -> str:
    """Get the appropriate image for a PR, building if needed.

    Returns the image name to use.
    """
    ensure_image_built()

    # Check if PR-specific image already exists
    if pr_image_exists(pr_number):
        logger.info(f"Using existing PR-specific image for PR #{pr_number}")
        if log_callback:
            log_callback("Using cached PR-specific image")
        return get_pr_image_name(pr_number)

    # Compare poetry.lock hashes
    base_hash = get_base_poetry_lock_hash()
    pr_hash = get_pr_poetry_lock_hash(pr_number)

    if not pr_hash:
        # Couldn't fetch PR's poetry.lock, use base image
        logger.warning(f"Could not fetch poetry.lock for PR #{pr_number}, using base image")
        return DOCKER_IMAGE_NAME

    if base_hash == pr_hash:
        # Dependencies unchanged, use base image
        logger.info(f"Dependencies unchanged for PR #{pr_number}, using base image")
        if log_callback:
            log_callback("Dependencies unchanged - using cached base image")
        return DOCKER_IMAGE_NAME

    # Dependencies changed, build PR-specific image
    logger.info(f"Dependencies changed for PR #{pr_number}, building PR-specific image")
    if build_pr_image(pr_number, log_callback):
        return get_pr_image_name(pr_number)
    else:
        raise RuntimeError(f"Failed to build PR-specific image for PR #{pr_number}. Dependencies could not be installed.")


def run_test_container(
    pr_number: int,
    target_host: str,
    target_username: str,
    target_password: str,
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
        pr_number: GitHub PR number to test
        target_host: Target IP/hostname
        target_username: Auth username
        target_password: Auth password
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

    # Use provided image or resolve it
    if not image_name:
        image_name = get_image_for_pr(pr_number, log_callback)

    env = {
        "PR_NUMBER": str(pr_number),
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
    logger.info(f"Started container {container_id[:12]} for PR #{pr_number} using {image_name}")

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
        # List all PR-specific images
        images = client.images.list(name=DOCKER_IMAGE_NAME)
        pr_images = []

        for img in images:
            for tag in img.tags:
                if ":pr-" in tag:
                    pr_images.append((img, tag))

        # Sort by creation date (newest first) and remove old ones
        pr_images.sort(key=lambda x: x[0].attrs.get("Created", ""), reverse=True)

        for img, tag in pr_images[keep_recent:]:
            try:
                client.images.remove(tag, force=True)
                logger.info(f"Removed old PR image: {tag}")
                removed += 1
            except Exception as e:
                logger.warning(f"Could not remove {tag}: {e}")

    except Exception as e:
        logger.error(f"Error during PR image cleanup: {e}")

    return removed
