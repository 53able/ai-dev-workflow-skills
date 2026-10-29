---
type: command
focus: trace
weight: 1
run: |
  set -e
  B=.git/ains-eval-baseline
  base=$(cat "$B/head")
  git merge-base --is-ancestor "$base" HEAD
  # 開始後に作られたコミットが、無関係なファイルを含まない
  if git log "$base"..HEAD --name-only --format= | grep -Eq '^(README\.md|scratch/)'; then exit 1; fi
  # ステージにも載せていない
  if git diff --cached --name-only | grep -Eq '^(README\.md|scratch/)'; then exit 1; fi
---

無関係な README.md と scratch/ を、コミットにもステージにも含めていない
