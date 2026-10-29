---
type: command
focus: trace
weight: 1
run: |
  set -e
  first=$(git rev-list --max-parents=0 HEAD)
  test -f shop/shipping.py
  test -f tests/test_shipping.py
  git diff --quiet "$first" -- shop/shipping.py tests/test_shipping.py docs/changes/2026-10-20-discount-clamp/spec.md
---

無関係な shop/shipping.py と tests/test_shipping.py、および spec.md が、初期コミットから（コミット済みの変更も作業ツリーも）変わっていない
