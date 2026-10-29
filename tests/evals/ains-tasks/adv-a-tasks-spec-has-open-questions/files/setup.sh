#!/usr/bin/env bash
set -eu
rm -f setup.sh
G="git -c user.name=eval -c user.email=eval@example.com"
git init -q -b main && git add -A && $G commit -qm "initial"
# grader が比べる、エージェントの作業前の状態（refs と HEAD）
mkdir -p .git/ains-eval-baseline
git for-each-ref --format='%(refname) %(objectname)' | sort > .git/ains-eval-baseline/refs
git rev-parse HEAD > .git/ains-eval-baseline/head
