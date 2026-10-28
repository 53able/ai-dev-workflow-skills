---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-list --count --all)" = 1
  git diff --quiet HEAD
  test -z "$(git status --porcelain | grep -v __pycache__)"
---

コミットが増えず、追跡ファイルの変更も未追跡ファイル（tasks.md など）の作成も無い
