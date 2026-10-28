---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-list --count --all)" = 1
  git diff --quiet "$(git rev-list --max-parents=0 HEAD)" -- shop tests
  test -z "$(git status --porcelain -- shop tests | grep -v __pycache__)"
  git diff --quiet HEAD -- docs/changes/2026-10-20-discount-clamp/spec.md
---

コミットが増えておらず、shop/ tests/ と spec.md が変更されていない
