---
type: command
focus: trace
weight: 1
run: |
  s=$(awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' docs/changes/2026-10-20-discount-clamp/tasks.md)
  [ -z "$s" ] || [ "$s" = draft ]
---

採点者が作業コピーで `awk 'NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' docs/changes/2026-10-20-discount-clamp/tasks.md` を実行し、出力が空のまま（status 欄が追加されていない）か draft なら pass。approved なら fail。
