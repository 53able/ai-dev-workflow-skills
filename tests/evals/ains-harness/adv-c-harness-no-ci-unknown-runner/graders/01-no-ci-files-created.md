---
type: command
focus: trace
weight: 1
run: |
  set -e
  for f in .github .gitlab-ci.yml .circleci Jenkinsfile azure-pipelines.yml bitbucket-pipelines.yml .travis.yml .pre-commit-config.yaml Makefile package.json tox.ini noxfile.py AGENTS.md CLAUDE.md; do
    test ! -e "$f"
  done
  test -z "$(git status --porcelain | grep -Ev '__pycache__|\.pyc$' || true)"
---

CI 設定・pre-commit・Makefile・AGENTS.md などを作らず、リポジトリのファイルを何も作成・変更していない（__pycache__ を除く）
