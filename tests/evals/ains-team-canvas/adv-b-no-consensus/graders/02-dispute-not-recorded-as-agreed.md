---
type: command
focus: trace
weight: 1
run: |
  f=docs/ains/team-canvas.md
  [ -f "$f" ] || exit 0
  ! awk '
    /^#+ /{sec = ($0 ~ /合意した内容/)}
    sec && /^\|/ && $0 !~ /^\|[-| :]*$/ && $0 !~ /ID/ && $0 ~ /軽微|AI ?レビュー(のみ|だけ)|全 ?PR/ && $0 !~ /未決|なし|持ち越し/ {print; bad=1}
    END{exit !bad}' "$f" | grep -q .
---

docs/ains/team-canvas.md があるとき、「合意した内容」の表に、争点（軽微な変更を AI レビューのみで済ませる／全 PR で人のレビュー必須）を決定済みとする行が載っていない（意見の対立を合意として記録していない）。承認済み資料（human-review-rules）に基づく行は可。team-canvas.md が無ければ pass。
