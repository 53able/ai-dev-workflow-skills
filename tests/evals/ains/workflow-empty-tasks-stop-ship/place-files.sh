#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/../router-does-not-edit/files/." .
printf "\n## タスク\n" >> docs/changes/2026-10-20-discount-clamp/spec.md
[ -f setup.sh ] && bash setup.sh
