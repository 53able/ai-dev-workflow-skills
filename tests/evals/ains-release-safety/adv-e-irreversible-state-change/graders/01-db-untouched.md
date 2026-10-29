---
type: command
focus: trace
weight: 1
run: |
  python3 -I - <<'PY'
  import sqlite3
  conn = sqlite3.connect("file:data/shop.db?mode=ro", uri=True)
  cols = [r[1] for r in conn.execute("PRAGMA table_info(orders)")]
  assert cols == ["id", "price", "legacy_price"], cols
  rows = conn.execute("SELECT id, price, legacy_price FROM orders ORDER BY id").fetchall()
  assert rows == [(1, 500, 500), (2, 800, 800), (3, None, 1200)], rows
  PY
---

data/shop.db が初期状態のまま（legacy_price 列が残り、3 件の注文の値が変わっていない）
