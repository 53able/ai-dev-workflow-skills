#!/usr/bin/env bash
set -eu
here=$(cd "$(dirname "$0")" && pwd)
# 土台（new-feature-stops-at-spec-gate の files/）をそのまま使う
cp -R "$here/../../ains-spec/new-feature-stops-at-spec-gate/files/." .
[ -f setup.sh ] && bash setup.sh
