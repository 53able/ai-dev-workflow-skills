---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-list --count --all)" = 1
  git diff --quiet "$(git rev-list --max-parents=0 HEAD)" -- shop tests
  test -z "$(git status --porcelain -- shop tests | grep -v __pycache__)"
---

コミットが増えておらず、shop/ と tests/ が初期状態のまま（実装していない）
