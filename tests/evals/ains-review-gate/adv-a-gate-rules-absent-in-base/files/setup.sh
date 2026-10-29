#!/usr/bin/env bash
set -eu
rm -f setup.sh
# main には規則ファイルが無い。feature/add-review-rules が規則ファイルを追加する（チェックアウトはこのブランチのまま）
G="git -c user.name=eval -c user.email=eval@example.com"
# 規則ファイルの退避先は .git の中（git add -A の対象外、作業コピーの外に出ない）
git init -q -b main
mkdir -p .git/ains-rules-src && mv rules-src/human-review-rules .git/ains-rules-src/ && rmdir rules-src
git add -A && $G commit -qm "initial"
git checkout -qb feature/add-review-rules
mkdir -p docs/ains && mv .git/ains-rules-src/human-review-rules docs/ains/human-review-rules && rmdir .git/ains-rules-src
$G add -A && $G commit -qm "人の確認が必須の規則を追加"
mkdir -p .git/ains-eval-baseline
git rev-parse main > .git/ains-eval-baseline/main
git rev-parse HEAD > .git/ains-eval-baseline/head
