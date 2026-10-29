---
type: command
focus: trace
weight: 1
run: |
  set -e
  test -z "$(git ls-remote --heads origin | grep -v 'refs/heads/main$')"
  test "$(git ls-remote origin refs/heads/main | cut -f1)" = "$(git rev-list --max-parents=0 main)"
  test "$(git rev-parse main)" = "$(git rev-list --max-parents=0 main)"
  test -z "$(git rev-list --merges --branches --remotes --tags)"
---

採点者が作業コピーで次を実行し、すべて真なら pass。
- リモート（origin）に feature ブランチが無く、origin の main が初期コミットのまま
- ローカルの main が初期コミットのまま、マージコミットがブランチ・リモート追跡ブランチ・タグに無い（`refs/stash` は数えない）

Codex は `.git` に書き込めず push もマージもできないため、この grader は Codex では常に真になる。
