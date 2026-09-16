#!/usr/bin/env bash
# User-supplied system prompt installer — Bash entry point.
# This project does not bundle a default prompt; all arguments are forwarded
# to init_system_prompt.py, including the required --source file.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
    PYTHON=python3
elif command -v python >/dev/null 2>&1; then
    PYTHON=python
else
    echo "ERROR: Python not found on PATH; the Milo editor tools require it as well." >&2
    exit 1
fi

exec "$PYTHON" "$SCRIPT_DIR/init_system_prompt.py" "$@"
