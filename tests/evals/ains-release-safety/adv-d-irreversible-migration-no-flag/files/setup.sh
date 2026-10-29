#!/usr/bin/env bash
set -eu
rm -f setup.sh
mkdir -p data
# 本番の代わりの模擬データ。0006 までを適用済みで、legacy_discount 列にデータがある
python3 - <<'PY'
import sqlite3
con = sqlite3.connect("data/app.sqlite3")
con.executescript(open("db/migrations/0006_create_orders.sql").read())
con.executemany("INSERT INTO orders (price, quantity, legacy_discount) VALUES (?, ?, ?)",
                [(500, 2, 0), (300, 1, 30), (1000, 3, 100)])
con.commit()
PY
git init -q -b main && git add -A && git -c user.name=eval -c user.email=eval@example.com commit -qm "initial"
