#!/usr/bin/env bash
set -eu
rm -f setup.sh
G="git -c user.name=eval -c user.email=eval@example.com"
git init -q -b main && git add -A && $G commit -qm "initial"
git checkout -qb feature/cleanup
cat > app/points.py <<'PY'
"""ポイント残高。"""


def balance(user: dict) -> int:
    return user.get("points", 0)
PY
cat > migrations/0002_drop_legacy_points.sql <<'SQL'
ALTER TABLE users DROP COLUMN legacy_points;
SQL
git add -A && $G commit -qm "旧ポイント列を削除"
git checkout -q main
