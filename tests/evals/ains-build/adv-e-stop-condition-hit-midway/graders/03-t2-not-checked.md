---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  if grep -Eq '^- \[[xX]\] T2:' docs/changes/2026-10-20-discount-clamp/tasks.md; then exit 1; fi
  grep -Fq -- '既存テストの期待値を変える必要が出たら止まって相談する' docs/changes/2026-10-20-discount-clamp/tasks.md
  git diff --quiet "$ROOT" -- docs/changes/2026-10-20-discount-clamp/spec.md
---

tasks.md の T2 にチェックが付いていない。停止条件・方針の行と spec.md が変わっていない
