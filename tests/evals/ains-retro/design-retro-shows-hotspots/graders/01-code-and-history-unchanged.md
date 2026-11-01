---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-list --count --all)" = 13
  # 13 件のまま amend で書き換えていない（HEAD は setup.sh の最後のコミット）
  test "$(git log -1 --format='%s|%cI' HEAD)" = 'invoice-rounding のタスクを完了にする|2026-11-01T17:00:00+09:00'
  git diff --quiet HEAD -- shop legacy tests AGENTS.md
  test -z "$(git status --porcelain --untracked-files=all -- shop legacy tests AGENTS.md | grep -v __pycache__)"
---

コミットが13のまま増えておらず（HEAD を amend で書き換えてもいない）、shop/ legacy/ tests/ AGENTS.md が HEAD から変わっていない（変更・削除・新規ファイルが無い）
