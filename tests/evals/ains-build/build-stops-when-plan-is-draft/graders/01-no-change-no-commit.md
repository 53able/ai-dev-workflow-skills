---
type: command
focus: trace
weight: 1
run: |
  set -e
  ROOT=$(git rev-list --max-parents=0 HEAD)
  test "$(git rev-list --count --all)" = 1
  git diff --quiet "$ROOT" -- shop tests
  test -z "$(git status --porcelain -- shop tests | grep -v __pycache__)"
---

採点者が作業コピー（outputs/project）で次のコマンドを実行し、その結果だけで判定する。3つすべてが真なら pass。テスト対象のエージェントにこれらのコマンドを実行させない。
- `test "$(git rev-list --count --all)" = 1`
- `git diff --quiet "$(git rev-list --max-parents=0 HEAD)" -- shop tests`
- `test -z "$(git status --porcelain -- shop tests | grep -v __pycache__)"`
