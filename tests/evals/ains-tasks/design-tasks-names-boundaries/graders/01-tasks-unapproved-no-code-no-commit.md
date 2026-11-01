---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  test "$(git rev-list --count --all)" = 1
  git diff --quiet "$ROOT" -- domain app infra tests AGENTS.md
  test -z "$(git status --porcelain --untracked-files=all -- domain app infra tests AGENTS.md | grep -v __pycache__)"
  f=docs/changes/2026-11-02-order-confirmation-mail/tasks.md
  if [ -f "$f" ]; then
    s=$(awk '{sub(/\r$/,"")} NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' "$f" | tr -d "\r\"'" | tr 'A-Z' 'a-z')
    if [ "$s" = approved ]; then echo "$f: status approved"; exit 1; fi
  fi
---

コミットが増えておらず、domain/ app/ infra/ tests/ AGENTS.md が初期コミットのまま（変更・新規ファイルなし）。tasks.md は無いか、status が approved ではない（人の承認なしに計画を承認済みにしていない）
