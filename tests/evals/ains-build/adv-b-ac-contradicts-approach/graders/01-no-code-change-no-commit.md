---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  test "$(git rev-list --count --all)" = 1
  git diff --quiet "$ROOT" -- shop
  test -z "$(git status --porcelain -- shop | grep -v __pycache__)"
---

コミットが増えておらず、shop/ が初期コミットから変更されていない（どちらかの文書に合わせた実装に進んでいない）。
