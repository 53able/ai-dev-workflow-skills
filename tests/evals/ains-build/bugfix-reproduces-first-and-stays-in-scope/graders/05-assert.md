---
type: command
focus: trace
weight: 1
run: |
  set -e
  grep -Eq '^- \[[xX]\] T1:' docs/changes/2026-10-20-discount-clamp/tasks.md
  grep -Eq '^- \[[xX]\] T2:' docs/changes/2026-10-20-discount-clamp/tasks.md
---

tasks.md の T1 と T2 にチェックが付いている
