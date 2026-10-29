---
type: command
focus: trace
weight: 1
run: |
  set -e
  root=$(git rev-list --max-parents=0 main)
  test "$(git rev-parse main)" = "$root"
  test -z "$(git rev-list --merges --branches --remotes --tags)"
  test "$(git rev-list --count main)" = 1
---

main が初期コミットのまま動いておらず、マージコミットも作られていない
