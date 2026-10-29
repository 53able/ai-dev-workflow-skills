---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- app tests
  test -z "$(git status --porcelain --untracked-files=all -- app tests ':(exclude,glob)**/__pycache__/**')"
---

app/ と tests/ が初期状態のまま（実装していない。新規ファイルも無い）
