#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/../router-does-not-edit/files/." .
printf "\n- スキル起動：各工程の製品ネイティブ起動は利用者の明示的なコマンドに限る。通常参照からの工程実行も、利用者の明示起動を待つ。\n" >> AGENTS.md
[ -f setup.sh ] && bash setup.sh
