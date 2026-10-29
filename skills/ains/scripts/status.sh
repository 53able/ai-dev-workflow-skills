#!/usr/bin/env bash
# 変更ディレクトリごとに、spec の状態、計画の状態、未決事項の数、タスクの進捗を1行で表示する。
# 並びは変更 ID（日付で始まる）の新しい順。先頭行が最新の変更。
#
# usage: status.sh [<changes-root>]   （既定: docs/changes）
#   plan=approved|draft  tasks.md の status（status 欄が無ければ draft）
#   plan=-               tasks.md が無い（小さな変更、または計画前）
set -uo pipefail

root="${1:-docs/changes}"
[[ -d "$root" ]] || { echo "変更ディレクトリがない: $root"; exit 0; }

count() { local n; n=$(grep -cE "$1" "$2" 2>/dev/null) || true; echo "${n:-0}"; }
# front matter は1行目が --- で、閉じの --- があるファイルだけから読む。行末の CR と値の末尾の空白は除く。
# 閉じるまでに「key:」、「- 」で始まる項目、字下げ、# のコメント、空行のどれでもない行があれば front matter とみなさない（閉じ忘れと本文の --- を区別する）
fm_status() { awk '{sub(/\r$/,"")} NR==1 && /^---$/{fm=1; next} !fm{exit} /^---$/{print v; exit} !/^([^ \t#:-][^:]*:|-[ \t]|[ \t]|#|$)/{exit} !got && /^status:/{sub(/^status:[ \t]*/,""); sub(/[ \t]+$/,""); v=$0; got=1}' "$1"; }

found=0
while IFS= read -r d; do
  d="${d%/}"; spec="$d/spec.md"
  [[ -f "$spec" ]] || continue
  found=1
  status=$(fm_status "$spec")
  open_q=$(awk '/^## 未決事項/{f=1;next} /^## /{f=0} f && /^[[:space:]]*- [^[:space:]]/' "$spec" | wc -l | tr -d ' ')
  if [[ -f "$d/tasks.md" ]]; then
    tasks="$d/tasks.md"; plan=$(fm_status "$tasks"); plan="${plan:-draft}"
  else
    tasks="$spec"; plan="-"
  fi
  # 本文が空の雛形行（"- [ ] T1: "）は数えない
  done_n=$(count '^[[:space:]]*- \[[xX]\] T[0-9]+:[[:space:]]*[^[:space:]]' "$tasks")
  open_n=$(count '^[[:space:]]*- \[ \] T[0-9]+:[[:space:]]*[^[:space:]]' "$tasks")
  printf '%s  status=%s  plan=%s  未決=%s  tasks=%s/%s\n' "$(basename "$d")" "${status:-?}" "$plan" "$open_q" "$done_n" "$((done_n + open_n))"
done < <(ls -1d "$root"/*/ 2>/dev/null | sort -r)
(( found )) || echo "spec.md のある変更がない: $root"
exit 0
