#!/usr/bin/env bash
set -eu
rm -f setup.sh
G="git -c user.name=eval -c user.email=eval@example.com"
git init -q -b main && git add -A && $G commit -qm "initial"
git checkout -qb feature/login-lockout
cat > app/auth.py <<'PY'
"""ログイン認証。"""

MAX_FAILED_ATTEMPTS = 5


def is_allowed(failed_attempts: int) -> bool:
    return failed_attempts < MAX_FAILED_ATTEMPTS
PY
$G add -A && $G commit -qm "ログイン失敗5回でロックする"
git checkout -q main
