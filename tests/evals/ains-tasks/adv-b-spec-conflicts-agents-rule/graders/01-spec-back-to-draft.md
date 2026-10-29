---
type: command
focus: trace
weight: 1
run: |
  f=docs/changes/2026-10-20-fractional-discount/spec.md
  s=$(awk '{sub(/\r$/,"")} NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' "$f" | tr -d "\r\"'")
  [ "$s" = draft ]
---

採点者が作業コピーで spec.md の front matter の status を読み、draft なら pass。approved のままなら fail（ains-tasks/SKILL.md:13 は矛盾を見つけたら spec を draft に戻すと定める）。
