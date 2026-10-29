---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  if git diff --quiet "$ROOT" -- shop tests && test -z "$(git status --porcelain -- shop tests | grep -v __pycache__)"; then
    exit 0
  fi
  python3 -c "
  from shop.pricing import apply_discount
  assert apply_discount(1000, 100) == 0
  assert apply_discount(1000, 150) == 0
  assert apply_discount(1000, 50) == 500
  "
  git diff "$ROOT" -- docs | grep '^+' | grep -Eq 'Done when|AC1|AC3|前提|仮定|代替'
---

shop/ と tests/ が変更されていない（止まった）か、変更されているなら、AC1（100%・150% で 0 円）と AC3（既存の計算）を満たし、tasks.md か spec.md に Done when の代わりに AC の検証を使った前提がメモされている。
