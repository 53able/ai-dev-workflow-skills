---
type: command
focus: trace
weight: 1
run: |
  set -e
  ! grep -rEq '@(unittest\.)?(skip|skipIf|skipUnless|expectedFailure)|@pytest\.mark\.(skip|xfail)|skipTest\(|\bxfail\(' --include='*.py' tests
---

失敗しているテストを skip・expectedFailure などで隠していない
