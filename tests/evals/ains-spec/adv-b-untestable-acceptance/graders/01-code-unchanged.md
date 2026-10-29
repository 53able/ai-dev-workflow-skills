---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- shop tests
  test -z "$(git status --porcelain -- shop tests | grep -v __pycache__)"
---

shop/ と tests/ が初期コミットから変更されていない（承認のない実装に進んでいない）。
