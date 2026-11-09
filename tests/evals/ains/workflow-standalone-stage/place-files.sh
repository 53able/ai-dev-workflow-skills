#!/usr/bin/env bash
set -eu
cp -R "$(dirname "$0")/../router-does-not-edit/files/." .
[ -f setup.sh ] && bash setup.sh
