---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-parse main)" = "$(git rev-list --max-parents=0 main)"
---

main ブランチの HEAD が初期コミットのまま（マージされていない）
