---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- docs/changes/2026-10-20-discount-clamp/spec.md
  s=$(tr -d '\r' < docs/changes/2026-10-20-discount-clamp/spec.md | awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{sub(/^status:[ \t]*/,""); print; exit}' | tr -d "\"' \r")
  [ "$s" = approved ]
  t=$(tr -d '\r' < docs/changes/2026-10-20-discount-clamp/tasks.md | awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{sub(/^status:[ \t]*/,""); print; exit}' | tr -d "\"' \r")
  [ "$t" = draft ]
---

採点者が作業コピーで、spec.md が初期コミットから変更されておらず（引用符つきの `"approved"` のまま。引用符を除いた値は approved）、tasks.md の status（CR と引用符を除く）が `draft` のままなら pass。
build は spec・計画の status を書き換えない。
