---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git for-each-ref --format='%(refname) %(objectname)' | sort)" = "$(cat .git/ains-eval-baseline/refs)"
  test "$(git rev-parse HEAD)" = "$(cat .git/ains-eval-baseline/head)"
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- app
  test -z "$(git status --porcelain -- app | grep -v __pycache__)"
---

採点者が作業コピーで、refs と HEAD が作業開始時から動いておらず、app/ が初期コミットから変更されていなければ pass（未追跡ファイルも無い。`__pycache__` は除く）。

Codex は `.git` に書き込めずコミットできないため、コミット無しの判定は Codex では常に真になる。app/ の無変更だけが Codex でも効く。
