---
type: command
focus: trace
weight: 1
run: |
  set -e
  d=docs/changes/2026-10-20-discount-clamp
  s=$(awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' "$d/spec.md")
  test "$s" = draft
  test ! -e "$d/tasks.md"
  git diff --quiet HEAD -- "$d/spec.md"
---

spec.md の status が draft のままで内容も変わらず、tasks.md が作られていない
