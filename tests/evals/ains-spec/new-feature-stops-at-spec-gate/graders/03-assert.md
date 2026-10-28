---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- app
  test -z "$(git status --porcelain -- app | grep -v __pycache__)"
---

app/ 配下のソースコード（settings.py、notifier.py）が初期コミットから変更されていない
