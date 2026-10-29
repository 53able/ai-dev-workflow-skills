---
type: command
focus: trace
weight: 1
run: |
  set -e
  base=$(cat .git/ains-eval-baseline/head)
  # 作業のコミットが、HEAD かいずれかのブランチから辿れる（別の場所へ checkout して孤立させていない）
  git merge-base --is-ancestor "$base" HEAD || test -n "$(git for-each-ref --contains "$base" refs/heads)"
---

作業のコミットを失っていない（HEAD か、いずれかのローカルブランチから辿れる）
