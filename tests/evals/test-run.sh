#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
# Only top-level test_*.py: case fixtures under */*/files/tests/ must not be collected.
cd "$here"
exec uv run --locked --project "$here/../.." python -m unittest discover -s "$here" -t "$here" -p 'test_*.py' "$@"
