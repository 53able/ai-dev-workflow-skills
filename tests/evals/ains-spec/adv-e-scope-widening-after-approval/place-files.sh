#!/usr/bin/env bash
set -eu
here=$(cd "$(dirname "$0")" && pwd)
# 土台（new-feature-stops-at-spec-gate の files/）に、このケースの差分だけを重ねる
cp -R "$here/../../ains-spec/new-feature-stops-at-spec-gate/files/." .
rm -f setup.sh
cp -R "$here/files/." .
[ -f setup.sh ] && bash setup.sh
