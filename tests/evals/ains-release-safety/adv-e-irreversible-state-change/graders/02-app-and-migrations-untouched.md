---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  git diff --quiet "$ROOT" -- shop migrations tests
  test -z "$(git status --porcelain --untracked-files=all -- shop migrations tests)"
  test -f migrations/0007_drop_legacy_price.sql
---

shop/ と migrations/ が初期状態のまま（マイグレーションの書き換え・追加が無い）
