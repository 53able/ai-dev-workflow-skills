#!/usr/bin/env bash
set -eu
rm -f setup.sh
export GIT_AUTHOR_NAME=eval GIT_AUTHOR_EMAIL=eval@example.com GIT_COMMITTER_NAME=eval GIT_COMMITTER_EMAIL=eval@example.com
export GIT_AUTHOR_DATE='2026-11-02T09:00:00+09:00' GIT_COMMITTER_DATE='2026-11-02T09:00:00+09:00'
git init -q -b main && git add -A && git commit -qm "initial"
