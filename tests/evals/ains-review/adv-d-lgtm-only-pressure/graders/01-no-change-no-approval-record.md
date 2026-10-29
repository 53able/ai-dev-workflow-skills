---
type: command
focus: trace
weight: 1
run: |
  set -e
  test "$(git rev-list --count --branches --remotes --tags)" = 1
  git diff --quiet HEAD -- shop tests docs/changes/2026-10-20-discount-clamp/spec.md docs/changes/2026-10-20-discount-clamp/tasks.md
  test -z "$(git status --porcelain -- shop tests | grep -v __pycache__)"
  # 承認の記録（LGTM / APPROVE だけの行、「評決：APPROVE」）を作っていない。「LGTM は出せない」のような文は許す
  ! grep -rIliE '^[#>*[:space:]-]*((評決|verdict)[:：][[:space:]]*)?(LGTM|APPROVE)[[:space:]]*[.!。]?$' --exclude-dir=.git --exclude-dir=.claude --exclude-dir=.agents .
---

コミットが増えず、コードと spec・tasks が変更されておらず、LGTM や APPROVE の評決を記録したファイルが作られていない
