#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/files/." .
[ -f setup.sh ] && bash setup.sh
