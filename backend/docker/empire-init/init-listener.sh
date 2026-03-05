#!/bin/sh
set -eu

# Initialize an Empire HTTP listener for NetExec e2e tests.
# Run this after the Empire container is healthy.
#
# Usage: ./init-listener.sh [empire_host] [empire_port]
#
# POSIX sh only — no python3 or bash required (runs in curlimages/curl).

EMPIRE_HOST="${1:-127.0.0.1}"
EMPIRE_PORT="${2:-1337}"
BASE_URL="http://${EMPIRE_HOST}:${EMPIRE_PORT}"

echo "Waiting for Empire at ${BASE_URL}..."
i=0
while [ "$i" -lt 30 ]; do
    if curl -sf "${BASE_URL}/" > /dev/null 2>&1; then
        echo "Empire is ready."
        break
    fi
    i=$((i + 1))
    if [ "$i" -eq 30 ]; then
        echo "ERROR: Empire not available after 30 attempts."
        exit 1
    fi
    sleep 2
done

# Authenticate — Empire's default creds are empireadmin/password123
echo "Authenticating to Empire..."
AUTH_RESPONSE=$(curl -sf -X POST "${BASE_URL}/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=empireadmin&password=password123")

# Extract access_token with sed (no python needed)
TOKEN=$(echo "$AUTH_RESPONSE" | sed 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/')

if [ -z "$TOKEN" ]; then
    echo "ERROR: Failed to get auth token."
    exit 1
fi
echo "Got auth token."

# Check if listener already exists
LISTENERS=$(curl -sf -H "Authorization: Bearer ${TOKEN}" "${BASE_URL}/api/v2/listeners")
if echo "$LISTENERS" | grep -q '"name":"http-listener"'; then
    echo "Listener 'http-listener' already exists. Skipping."
    exit 0
fi

# Create HTTP listener
echo "Creating HTTP listener..."
curl -sf -X POST "${BASE_URL}/api/v2/listeners" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{
        "name": "http-listener",
        "template": "http",
        "options": {
            "Name": "http-listener",
            "Host": "http://0.0.0.0",
            "BindIP": "0.0.0.0",
            "Port": "8080"
        }
    }'

echo ""
echo "Empire HTTP listener created successfully."
