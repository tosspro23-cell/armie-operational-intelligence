#!/bin/sh
set -eu

test -n "${CODEX_API_KEY:-}" || { echo "CODEX_API_KEY is required" >&2; exit 64; }
test -n "${SESSION_REMOTE_URL:-}" || { echo "SESSION_REMOTE_URL is required" >&2; exit 64; }
test -n "${SESSION_ENVIRONMENT_ID:-}" || { echo "SESSION_ENVIRONMENT_ID is required" >&2; exit 64; }

exec codex exec-server \
  --remote "$SESSION_REMOTE_URL" \
  --environment-id "$SESSION_ENVIRONMENT_ID"
