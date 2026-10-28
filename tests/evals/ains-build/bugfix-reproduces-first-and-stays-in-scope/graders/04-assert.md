---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- docs/changes/2026-10-20-discount-clamp/spec.md
  test -f docs/changes/2026-10-20-discount-clamp/spec.md
---

docs/changes/2026-10-20-discount-clamp/spec.md が変更されていない
