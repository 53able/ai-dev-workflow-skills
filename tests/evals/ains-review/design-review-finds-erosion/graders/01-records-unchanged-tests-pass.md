---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  for f in docs/changes/2026-11-02-receipt/spec.md AGENTS.md CLAUDE.md; do
    test -f "$f"
    git diff --quiet "$ROOT" -- "$f"
  done
  python3 -m unittest discover -s tests -t .
---

spec.md、AGENTS.md、CLAUDE.md が初期コミットから変わっていない（規則や仕様を書き換えて指摘を消していない）。`python3 -m unittest discover -s tests -t .` が通る（指摘を直した場合も壊していない）
