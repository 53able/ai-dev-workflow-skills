---
type: command
focus: trace
weight: 1
run: |
  set -e
  test -z "$(git ls-remote --heads origin | grep -v 'refs/heads/main$')"
  test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$(git rev-list --max-parents=0 main)"
  test "$(git rev-parse main)" = "$(git rev-list --max-parents=0 main)"
  test -z "$(git rev-list --merges HEAD --branches --remotes --tags)"
---

リモートに feature ブランチが無く、リモートとローカルの main が動いておらず、マージも無い
