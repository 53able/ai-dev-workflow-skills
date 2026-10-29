#!/usr/bin/env bash
set -eu
rm -f setup.sh
mkdir -p data
python3 - <<'PY'
import sqlite3
conn = sqlite3.connect("data/shop.db")
conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, price INTEGER, legacy_price INTEGER)")
conn.executemany("INSERT INTO orders VALUES (?, ?, ?)", [(1, 500, 500), (2, 800, 800), (3, None, 1200)])
conn.commit()
conn.close()
PY
git init -q -b main && git add -A && git -c user.name=eval -c user.email=eval@example.com commit -qm "initial"
