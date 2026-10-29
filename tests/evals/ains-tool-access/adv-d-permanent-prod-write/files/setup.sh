#!/usr/bin/env bash
set -eu
rm -f setup.sh
git init -q -b main && git add -A && git -c user.name=eval -c user.email=eval@example.com commit -qm "initial"
