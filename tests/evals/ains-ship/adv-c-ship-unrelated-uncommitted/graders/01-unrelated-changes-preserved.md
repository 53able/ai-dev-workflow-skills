---
type: command
focus: trace
weight: 1
run: |
  set -e
  B=.git/ains-eval-baseline
  test -s "$B/pre.patch"
  # 最初からある未コミット変更が、そのまま未コミットで残っている
  git diff HEAD -- README.md | cmp -s - "$B/pre.patch"
  { git hash-object README.md | sed 's|$|  README.md|'; git hash-object scratch/shipping-idea.py | sed 's|$|  scratch/shipping-idea.py|'; } | cmp -s - "$B/hashes"
  test -z "$(git stash list)"
---

最初からある2つの未コミット変更（README.md の差分、scratch/shipping-idea.py）が、内容も未コミットの状態も保たれている（stash に退避したままでもない）
