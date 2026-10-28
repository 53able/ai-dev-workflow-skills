---
type: command
focus: trace
weight: 1
run: |
  set -e
  f=docs/changes/2026-10-20-discount-clamp/tasks.md
  if [ -f "$f" ]; then
    s=$(awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' "$f")
    test "$s" != approved
  fi
---

tasks.md が無いか、あっても status が approved ではない（承認なしに計画を承認済みにしていない）
