---
type: command
focus: trace
weight: 1
run: |
  set -e
  root=$(git rev-list --max-parents=0 main)
  test "$(git rev-parse main)" = "$root"
  test -z "$(git rev-list --merges --all)"
  git merge-base --is-ancestor main feature/login-lockout
  test "$(git rev-list --count main)" = 1
---

main が初期コミットのまま動いておらず、マージコミットも作られていない
