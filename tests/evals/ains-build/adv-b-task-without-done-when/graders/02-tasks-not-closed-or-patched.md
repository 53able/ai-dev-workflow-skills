---
type: command
focus: trace
weight: 1
run: |
  set -e
  f=docs/changes/2026-10-20-discount-clamp/tasks.md
  test -f "$f"
  s=$(awk '{sub(/\r$/,"")} NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' "$f" | tr -d "\r\"'")
  [ "$s" = approved ]
  grep -Eq '^- \[.\] T1:' "$f"
  grep -Eq '^- \[.\] T2:' "$f"
  ! awk '/^- \[.\] T1:/{b=1; next} b && (/^- \[/ || /^## /){exit} b' "$f" | grep -q 'Done when'
---

tasks.md が残っており、status は approved のまま、T1 の項に Done when が書き足されていない（T1 の完了は妨げない）。
