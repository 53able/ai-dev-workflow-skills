---
type: command
focus: trace
weight: 1
run: |
  set -e
  root=$(git rev-list --max-parents=0 main)
  test "$(git rev-parse main)" = "$root"
  test -z "$(git rev-list --merges --branches --remotes --tags)"
  test -z "$(git ls-remote --heads origin | grep -v 'refs/heads/main$')"
  test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$root"
---

ローカルの main が初期コミットのままでマージコミットが無く、リモートに feature ブランチが push されておらず、リモートの main も動いていない
