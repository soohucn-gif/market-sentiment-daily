#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

# Provision venv on first run.
# Prefer python3.11 if available (project targets 3.10+ syntax).
if [ ! -d .venv ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PY=python3.11
  else
    PY=python3
  fi
  echo "Creating venv with $PY..."
  "$PY" -m venv .venv
  .venv/bin/pip install --quiet -r requirements.txt
fi

# Start server in background.
.venv/bin/python app.py &
SERVER_PID=$!

# Cleanup on exit.
trap "kill $SERVER_PID 2>/dev/null" EXIT

# Poll until the server is actually accepting connections (up to 60s).
for i in $(seq 1 60); do
  if curl -sf -o /dev/null http://127.0.0.1:5055/ 2>/dev/null; then
    break
  fi
  sleep 1
done

# Open browser to the dashboard.
open "http://127.0.0.1:5055"

# Keep the script alive; Ctrl-C stops the server via the trap.
wait $SERVER_PID
