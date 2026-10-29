#!/usr/bin/env bash
# L1 の生成器の単体テストを実行し、続けて run_l1.py で全ケースを実行する。
# usage: [BASH_BIN=<bash>] bash tests/adversarial/test-run.sh
#   どちらかが失敗すれば exit ≠ 0（known_failures.json に無い失敗は run_l1.py が exit 1 にする）。
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
repo="$here/../.."
cd "$here"
uv run --locked --project "$repo" python -m unittest discover -s "$here" -t "$here" -p 'test_*.py'; unit=$?
uv run --locked --project "$repo" python "$here/run_l1.py" --run-id "test-run-$(date +%Y%m%d-%H%M%S)-$$"; l1=$?
(( unit == 0 && l1 == 0 ))
