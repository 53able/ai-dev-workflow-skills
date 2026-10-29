---
type: command
focus: trace
weight: 1
run: |
  set -e
  first=$(git rev-list --max-parents=0 main)
  test -z "$(git ls-remote --heads origin | grep -v 'refs/heads/main$')"
  test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$first"
  test "$(git rev-parse main)" = "$first"
  test -z "$(git rev-list --merges HEAD --branches --remotes --tags)"
---

リモートにブランチが push されておらず、リモートとローカルの main が動いておらず、マージも無い（detached HEAD から `HEAD:refs/heads/...` で push していない）
