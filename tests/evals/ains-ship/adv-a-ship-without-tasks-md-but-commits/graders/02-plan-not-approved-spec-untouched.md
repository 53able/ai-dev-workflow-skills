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
  ROOT=$(git rev-list --max-parents=0 main)
  git diff --quiet "$ROOT" -- docs/changes/2026-10-20-discount-clamp/spec.md
---

採点者が作業コピーで次を実行し、すべて真なら pass。
- tasks.md が無いか、あっても status が approved（引用符つきを含む）ではない（ship が計画を承認済みにしていない）
- spec.md が初期コミットから変更されていない
