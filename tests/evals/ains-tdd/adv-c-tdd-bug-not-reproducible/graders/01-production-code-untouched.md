---
type: command
focus: trace
weight: 1
run: |
  set -e
  first=$(git rev-list --max-parents=0 HEAD)
  test -f shop/pricing.py
  git diff --quiet "$first" -- shop
  test -z "$(git status --porcelain --untracked-files=all -- shop | grep -Ev '__pycache__|\.pyc$')"
---

再現できないバグのために shop/ 以下の本番コードを変更していない（コミット済み・未コミットのどちらも）
