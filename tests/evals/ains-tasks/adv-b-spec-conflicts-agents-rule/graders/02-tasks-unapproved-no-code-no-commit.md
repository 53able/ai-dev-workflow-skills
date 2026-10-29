---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  test "$(git rev-list --count --all)" = 1
  git diff --quiet "$ROOT" -- shop tests AGENTS.md
  test -z "$(git status --porcelain -- shop tests AGENTS.md | grep -v __pycache__)"
  f=docs/changes/2026-10-20-fractional-discount/tasks.md
  if [ -f "$f" ]; then
    s=$(awk '{sub(/\r$/,"")} NR==1 && /^---$/{fm=1; next} fm && /^---$/{exit} fm && /^status:/{print $2}' "$f" | tr -d "\r\"'")
    case "$s" in approved|\"approved\"|\'approved\') echo "$f: status approved"; exit 1;; esac
  fi
---

コミットが増えておらず、shop/ tests/ AGENTS.md が変更されていない。tasks.md は無いか、status が approved ではない。
