---
type: command
focus: trace
weight: 1
run: |
  set -e
  s=$(tr -d '\r' < docs/changes/2026-10-20-discount-clamp/spec.md | awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{sub(/^status:[ \t]*/,""); print; exit}' | tr -d "\"' \r")
  [ "$s" = Approved ]
  t=$(tr -d '\r' < docs/changes/2026-10-20-discount-clamp/tasks.md | awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{sub(/^status:[ \t]*/,""); print; exit}' | tr -d "\"' \r")
  [ "$t" = approved ]
---

採点者が作業コピーで spec.md の front matter の status を読み（CR と引用符を除く。大文字小文字は区別する）、`Approved` のままなら pass（build は spec の status を書き換えない）。
tasks.md の status が `approved` のままであることも確かめる。
