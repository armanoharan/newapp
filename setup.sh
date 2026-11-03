#!/usr/bin/env bash
# One-step setup for macOS/Linux: finds (or installs) Python 3.10+,
# creates .venv, installs dependencies, and starts the API.
set -euo pipefail
cd "$(dirname "$0")"

find_python() {
  for cmd in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" >/dev/null 2>&1 &&
       "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      command -v "$cmd"
      return 0
    fi
  done
  return 1
}

PY="$(find_python || true)"

if [ -z "$PY" ]; then
  echo "Python 3.10+ not found."
  if command -v brew >/dev/null 2>&1; then
    echo "Installing Python 3.12 with Homebrew..."
    brew install python@3.12
    PY="$(find_python || true)"
    [ -z "$PY" ] && PY="$(brew --prefix python@3.12)/bin/python3.12"
  else
    echo "Install Python 3.12 from https://www.python.org/downloads/ and run ./setup.sh again."
    exit 1
  fi
fi

echo "Using $PY ($("$PY" --version))"

# Recreate .venv if it was built with an old Python.
if [ -d .venv ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
  echo "Removing old .venv built with an outdated Python..."
  rm -rf .venv
fi
[ -d .venv ] || "$PY" -m venv .venv

.venv/bin/python -m pip install --upgrade pip --quiet
.venv/bin/python -m pip install -r requirements.txt --quiet

echo
echo "Setup complete."
echo "  Add the MCP server to Claude Code:"
echo "    claude mcp add b2b-crm -e CRM_API_URL=http://localhost:8000 -- \"$(pwd)/.venv/bin/python\" -m mcp_server"
echo
echo "Starting the API at http://localhost:8000/docs  (Ctrl+C to stop)"
exec .venv/bin/python -m uvicorn api.main:app --port 8000
