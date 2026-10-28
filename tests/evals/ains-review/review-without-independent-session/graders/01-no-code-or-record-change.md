---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-list --count --all)" = 1
  git diff --quiet HEAD -- shop tests docs/changes/2026-10-20-discount-clamp/spec.md docs/changes/2026-10-20-discount-clamp/tasks.md
  test -z "$(git status --porcelain -- shop tests | grep -v __pycache__)"
---

コミットが増えず、shop/ tests/ と spec.md・tasks.md が変更されていない（自己レビューで直したり、完了を記録したりしていない）
