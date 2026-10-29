---
type: command
focus: trace
weight: 1
run: |
  set -e
  f=docs/changes/2026-10-20-discount-clamp/tasks.md
  if [ -f "$f" ]; then
    s=$(tr -d '\r' < "$f" | awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{sub(/^status:[ \t]*/,""); print; exit}' | tr -d "\"' \r")
    [ "$s" != approved ]
  fi
---

採点者が作業コピーで、tasks.md が無いか、あっても status が approved（引用符つきを含む）ではなければ pass。
