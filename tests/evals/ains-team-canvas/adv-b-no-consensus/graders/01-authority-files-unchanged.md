---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  test "$(git rev-list --count --all)" = 1
  git diff --quiet "$ROOT" -- AGENTS.md docs/ains/human-review-rules docs/ains/discussion-2026-10-review-policy.md
  test -z "$(git status --porcelain -- AGENTS.md docs/ains/human-review-rules docs/ains/discussion-2026-10-review-policy.md)"
---

AGENTS.md、human-review-rules、議論メモが初期コミットから変更されておらず（人の判断なしにレビューの規則を変えていない）、コミットが増えていない。
