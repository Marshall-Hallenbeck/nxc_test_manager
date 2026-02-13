#!/bin/bash
set -e

cd /netexec

# Check if this is a PR-specific image (deps already installed) or base image
if [ -d ".git" ] && git rev-parse --verify "pr-${PR_NUMBER}" >/dev/null 2>&1; then
    echo "=== Using pre-built PR image with cached dependencies ==="
    git checkout -q "pr-${PR_NUMBER}"
else
    echo "=== Fetching PR #${PR_NUMBER} ==="
    # Initialize git repo and fetch just the PR
    rm -rf .git 2>/dev/null || true
    git init -q
    git remote add origin https://github.com/Pennyw0rth/NetExec.git
    git fetch --depth 1 origin "pull/${PR_NUMBER}/head:pr-${PR_NUMBER}"
    git checkout -q "pr-${PR_NUMBER}"

    # Check if dependencies changed by comparing poetry.lock
    echo "=== Checking dependencies ==="
    if [ -f /poetry.lock.base ] && diff -q poetry.lock /poetry.lock.base > /dev/null 2>&1; then
        echo "Dependencies unchanged - using cached installation"
    else
        echo "Dependencies changed - reinstalling with Poetry"
        poetry config virtualenvs.create false
        poetry install --no-interaction
        # Poetry bug: git deps pinned to HEAD can be silently dropped during update.
        # Force-reinstall them with pip as a workaround.
        grep -oP 'git\+https://[^"]+' pyproject.toml | xargs -r pip install --force-reinstall --no-deps
    fi
fi

# Verify critical dependencies are importable before running tests
echo "=== Verifying dependencies ==="
python -c "from nxc.connection import connection" 2>&1 || {
    echo "FATAL: Dependency verification failed. Cannot run tests."
    exit 1
}
echo "Dependencies OK"

echo "=== Running e2e tests against ${TARGET_HOST} ==="

# Build command with optional flags
CMD="python tests/e2e_tests.py -t \"${TARGET_HOST}\" -u \"${TARGET_USERNAME}\" -p \"${TARGET_PASSWORD}\""

# Add protocols if specified
if [ -n "$PROTOCOLS" ]; then
    # Convert comma-separated to space-separated for --protocols
    PROTO_ARGS=$(echo "$PROTOCOLS" | tr ',' ' ')
    CMD="$CMD --protocols $PROTO_ARGS"
fi

# Add optional flags
if [ -n "$USE_KERBEROS" ]; then
    CMD="$CMD -k"
fi

if [ -n "$VERBOSE" ]; then
    CMD="$CMD -v"
fi

if [ -n "$SHOW_ERRORS" ]; then
    CMD="$CMD -e"
fi

if [ -n "$LINE_NUMS" ]; then
    # Convert comma-separated to space-separated for --line-nums
    LINES_ARGS=$(echo "$LINE_NUMS" | tr ',' ' ')
    CMD="$CMD --line-nums $LINES_ARGS"
fi

if [ -n "$NOT_TESTED" ]; then
    CMD="$CMD --not-tested"
fi

if [ -n "$DNS_SERVER" ]; then
    CMD="$CMD --dns-server $DNS_SERVER"
fi

echo "Executing: $CMD"

# Use timeout to prevent infinite hangs (default: 1800s = 30 minutes)
TIMEOUT=${CONTAINER_TIMEOUT:-1800}
eval timeout --signal=TERM --kill-after=30 "$TIMEOUT" $CMD
EXIT_CODE=$?

if [ $EXIT_CODE -eq 124 ]; then
    echo "ERROR: Test execution timed out after ${TIMEOUT} seconds"
fi

exit $EXIT_CODE
