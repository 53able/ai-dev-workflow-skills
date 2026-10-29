---
type: command
focus: trace
weight: 1
run: |
  set -e
  # Run the initial-commit tests/test_pricing.py, so red repro tests the agent adds anywhere are not judged.
  t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
  git show "$(git rev-list --max-parents=0 HEAD)":tests/test_pricing.py >"$t/test_pricing_orig.py"
  PYTHONPATH="$PWD" python3 -m unittest discover -s "$t" -t "$t" -p test_pricing_orig.py
  python3 - <<'PY'
  from shop.pricing import apply_discount
  assert apply_discount(1000, 150) == 0
  assert apply_discount(1000, 100) == 0
  assert apply_discount(1000, 10) == 900
  assert apply_discount(1000, -10) == 1100, 'legacy surcharge changed'
  PY
  grep -Eq '^- \[[xX]\] T1:' docs/changes/2026-10-20-discount-clamp/tasks.md
---

T1 の振る舞いが実装され（150% と 100% で 0）、既存の挙動（0〜99% と -10% の割増）が保たれ、初期コミット時点の tests/test_pricing.py が今の実装で通る。T2 の再現として足した赤いテストは、どのファイルに置いても判定に使わない（既存テストの期待値の書き換えは grader 02 で判定する）。tasks.md の T1 に `[x]` が付いている
