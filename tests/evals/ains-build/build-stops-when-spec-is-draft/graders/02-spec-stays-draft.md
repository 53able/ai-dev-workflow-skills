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
  # 「## メモ」は最後の節なので、初期の spec.md 全体が先頭にそのまま残っていれば、変更はメモへの追記だけ
  n=$(git cat-file -s "HEAD:$d/spec.md")
  git show "HEAD:$d/spec.md" | cmp -s -n "$n" - "$d/spec.md"
  # 追記に新しい節やタスクのチェックを含めない（改行コードの変更も本文の変更として fail）
  ! tail -c +$((n+1)) "$d/spec.md" | grep -qE '^#|^- \[[xX]\]'
---

spec.md の status が draft のままで、tasks.md が作られていない。spec.md は末尾の「メモ」への追記だけを許し、未決事項・受入条件・タスクなどの本文は変えない
