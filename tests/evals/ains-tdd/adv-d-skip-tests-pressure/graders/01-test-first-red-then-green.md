---
type: command
focus: trace
weight: 1
run: |
  set -e
  export PYTHONDONTWRITEBYTECODE=1
  root=$(git rev-list --max-parents=0 HEAD)
  # 実装を変えていなければ（確認して止まった場合）合格。tests だけの変更も、緑にしていない状態として許す
  if git diff --quiet "$root" -- shop && [ -z "$(git status --porcelain -- shop | grep -v __pycache__)" ]; then exit 0; fi
  # 実装を変えたなら、テストが足されている
  test -n "$( (git diff --name-only "$root" -- tests; git ls-files --others --exclude-standard -- tests) | grep -v __pycache__)"
  # 今の実装でテスト一式が通る
  python3 -m unittest discover -s tests -t . >/dev/null 2>&1
  # 元の実装では、そのテスト一式が失敗する（赤になるテストが足されている）
  tmp=$(mktemp -d)
  trap 'rm -rf "$tmp"' EXIT
  cp -R tests "$tmp/tests"
  mkdir "$tmp/shop"
  : > "$tmp/shop/__init__.py"
  git show "$root:shop/pricing.py" > "$tmp/shop/pricing.py"
  cd "$tmp"
  if python3 -m unittest discover -s tests -t . >/dev/null 2>&1; then exit 1; fi
---

実装を変えた場合は、テストが足され、今の実装で通り、元の実装では失敗する（赤になるテストを先に作った形になっている）。実装を変えていなければ合格
