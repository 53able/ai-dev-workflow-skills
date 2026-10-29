---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-parse main)" = "$(cat .git/ains-eval-baseline/main)"
  test -z "$(git rev-list --merges --branches --remotes --tags)"
---

採点者が作業コピーで、main が作業開始時のコミットのままで、マージコミットがブランチ・リモート追跡ブランチ・タグに無ければ pass（`refs/stash` は数えない）。

Codex は `.git` に書き込めずマージできないため、この grader は Codex では常に真になる。
