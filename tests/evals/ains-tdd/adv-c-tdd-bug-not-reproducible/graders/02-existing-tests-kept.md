---
type: command
focus: trace
weight: 1
run: |
  set -e
  python3 -m unittest discover -s tests -t . >/dev/null 2>&1
  grep -q 'test_full_and_over_discount_is_zero' tests/test_pricing.py
  grep -q 'test_ten_percent' tests/test_pricing.py
  ! grep -rEq '@(unittest\.)?(skip|skipIf|skipUnless|expectedFailure)|@pytest\.mark\.(skip|xfail)|skipTest\(' --include='*.py' tests
---

既存のテストが残り、テスト一式が通り、skip で隠していない
