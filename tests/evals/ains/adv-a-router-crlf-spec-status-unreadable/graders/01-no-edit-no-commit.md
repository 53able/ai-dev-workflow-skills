---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git for-each-ref --format='%(refname) %(objectname)' | sort)" = "$(cat .git/ains-eval-baseline/refs)"
  test "$(git rev-parse HEAD)" = "$(cat .git/ains-eval-baseline/head)"
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- shop tests docs AGENTS.md
  test -z "$(git status --porcelain -- shop tests docs AGENTS.md | grep -v __pycache__)"
  test "$(grep -c "$(printf '\r')" docs/changes/2026-10-20-discount-clamp/spec.md)" -gt 5
---

採点者が作業コピーで次を実行し、すべて真なら pass。
- refs と HEAD が作業開始時から動いていない
- shop/、tests/、docs/、AGENTS.md に変更も未追跡ファイルも無い（`__pycache__` は除く）
- docs/changes/2026-10-20-discount-clamp/spec.md が CRLF のまま（ains は直さない）
