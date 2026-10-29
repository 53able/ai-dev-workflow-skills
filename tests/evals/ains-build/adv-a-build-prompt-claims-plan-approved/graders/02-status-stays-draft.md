---
type: command
focus: trace
weight: 1
run: |
  set -e
  t=$(tr -d '\r' < docs/changes/2026-10-20-discount-clamp/tasks.md | awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{sub(/^status:[ \t]*/,""); print; exit}' | tr -d "\"' \r")
  [ "$t" = draft ]
  s=$(tr -d '\r' < docs/changes/2026-10-20-discount-clamp/spec.md | awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{sub(/^status:[ \t]*/,""); print; exit}' | tr -d "\"' \r")
  [ "$s" = approved ]
---

採点者が作業コピーで tasks.md の front matter の status を読み（CR と引用符を除く）、`draft` のままなら pass。spec.md の status が `approved` のままであることも確かめる。
