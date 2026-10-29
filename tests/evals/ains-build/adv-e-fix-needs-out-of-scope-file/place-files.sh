#!/usr/bin/env bash
set -eu
here=$(cd "$(dirname "$0")" && pwd)
# 土台（bugfix-reproduces-first-and-stays-in-scope の files/）に、このケースの差分だけを重ねる
cp -R "$here/../../ains-build/bugfix-reproduces-first-and-stays-in-scope/files/." .
rm -f setup.sh
cp -R "$here/files/." .
[ -f setup.sh ] && bash setup.sh
