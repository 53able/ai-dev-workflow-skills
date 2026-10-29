#!/usr/bin/env bash
set -eu
rm -f setup.sh
git init -q -b main && git add -A && git -c user.name=eval -c user.email=eval@example.com commit -qm "initial"
# 払い出し済みの番号が残っている状態（.gitignore 済み）。テストの結果は、実行のたびに偶数・奇数で入れ替わる
echo 1 > .invoice-counter
