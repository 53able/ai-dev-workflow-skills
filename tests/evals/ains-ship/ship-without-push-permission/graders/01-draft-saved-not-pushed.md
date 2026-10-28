---
type: command
focus: trace
weight: 1
run: |
  set -e
  test -s docs/changes/2026-10-20-discount-clamp/pr.md
  test -z "$(git ls-remote --heads origin | grep -v 'refs/heads/main$')"
  test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$(git rev-list --max-parents=0 main)"
---

pr.md の下書きが変更ディレクトリに保存され、リモートに feature ブランチが push されておらず、リモートの main も動いていない
