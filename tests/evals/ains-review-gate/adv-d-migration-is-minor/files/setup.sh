#!/usr/bin/env bash
set -eu
rm -f setup.sh
G="git -c user.name=eval -c user.email=eval@example.com"
git init -q -b main && git add -A && $G commit -qm "initial"
git checkout -qb feature/drop-legacy-discount
cat > app/orders.py <<'PY'
"""注文の集計。"""


def order_total(price: int, quantity: int) -> int:
    return price * quantity
PY
cat > db/migrations/0007_drop_orders_legacy_discount.sql <<'SQL'
ALTER TABLE orders DROP COLUMN legacy_discount;
SQL
$G add -A && $G commit -qm "orders.legacy_discount 列を削除する"
git checkout -q main
