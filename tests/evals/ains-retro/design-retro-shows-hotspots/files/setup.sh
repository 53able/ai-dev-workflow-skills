#!/usr/bin/env bash
set -eu
rm -f setup.sh
export GIT_AUTHOR_NAME=eval GIT_AUTHOR_EMAIL=eval@example.com GIT_COMMITTER_NAME=eval GIT_COMMITTER_EMAIL=eval@example.com
export GIT_AUTHOR_DATE='2026-10-01T10:00:00+09:00' GIT_COMMITTER_DATE='2026-10-01T10:00:00+09:00'
git init -q -b main
git add -A -- . ':(exclude)_history' && git commit -qm "initial"
# _history/NN/meta は1行目が日付、2行目がコミットメッセージ。files/ をそのまま重ねてコミットする（計13コミット）
for step in _history/*/; do
  date=$(sed -n 1p "$step/meta")
  msg=$(sed -n 2p "$step/meta")
  cp -R "$step/files/." .
  export GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date"
  git add -A -- . ':(exclude)_history' && git commit -qm "$msg"
done
rm -rf _history
