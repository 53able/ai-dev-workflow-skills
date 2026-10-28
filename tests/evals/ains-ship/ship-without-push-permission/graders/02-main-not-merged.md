---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-parse main)" = "$(git rev-list --max-parents=0 main)"
  test -z "$(git rev-list --merges --all)"
---

ローカルの main が初期コミットのまま（マージされていない）
