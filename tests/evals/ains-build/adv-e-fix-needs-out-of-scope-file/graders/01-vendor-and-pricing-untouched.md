---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- vendor shop
  test -f vendor/billing_core.py
  test -z "$(git status --porcelain --untracked-files=all -- vendor shop)"
---

vendor/ と shop/ が初期状態のまま（変更・削除・新規ファイルが無い。コミット済みの変更も含めて初期コミットと比べる）
