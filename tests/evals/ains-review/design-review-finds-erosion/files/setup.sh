#!/usr/bin/env bash
set -eu
rm -f setup.sh
export GIT_AUTHOR_NAME=eval GIT_AUTHOR_EMAIL=eval@example.com GIT_COMMITTER_NAME=eval GIT_COMMITTER_EMAIL=eval@example.com
# base: 会計まで（spec と tasks は承認済み）
export GIT_AUTHOR_DATE='2026-11-01T10:00:00+09:00' GIT_COMMITTER_DATE='2026-11-01T10:00:00+09:00'
git init -q -b main && git add -A -- . ':(exclude)_head' && git commit -qm "initial"
# head: 領収書を出す実装（レビューの対象）
cp -R _head/. . && rm -rf _head
export GIT_AUTHOR_DATE='2026-11-02T15:00:00+09:00' GIT_COMMITTER_DATE='2026-11-02T15:00:00+09:00'
git add -A && git commit -qm "領収書を出す"
