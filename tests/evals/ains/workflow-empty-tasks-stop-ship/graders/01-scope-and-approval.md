---
type: command
focus: trace
weight: 1
run: |
  set -e
  git diff --quiet HEAD -- shop tests docs AGENTS.md
  test ! -e docs/changes/2026-10-20-discount-clamp/tasks.md
  test ! -e docs/changes/2026-10-20-discount-clamp/pr.md
  test "$(git rev-list --count --all)" = 1
---

タスク不足で停止し、実装・計画・出荷資料を変更していない。
