#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
exec uv run --locked --project "$here/../.." python "$here/test_status.py" "$@"
