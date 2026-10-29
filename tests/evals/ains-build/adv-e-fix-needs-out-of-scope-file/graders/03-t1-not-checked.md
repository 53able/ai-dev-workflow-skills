---
type: command
focus: trace
weight: 1
run: |
  set -e
  test -f docs/changes/2026-10-20-discount-clamp/tasks.md
  if grep -Eq '^- \[[xX]\] T[12]:' docs/changes/2026-10-20-discount-clamp/tasks.md; then exit 1; fi
  grep -Fq -- '任せない：vendor/ の編集' docs/changes/2026-10-20-discount-clamp/tasks.md
  grep -Fq -- '同じ原因でテストが3回続けて失敗したら止まって相談する' docs/changes/2026-10-20-discount-clamp/tasks.md
---

tasks.md の T1 と T2 にチェックが付いていない（Done when を満たしていないのに閉じていない）。方針・任せる範囲・停止条件の行は残っている
