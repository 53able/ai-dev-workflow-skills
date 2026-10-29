"""注文の読み出し。"""
import sqlite3


def order_price(conn: sqlite3.Connection, order_id: int) -> int:
    """price が入っていれば price、無ければ旧列の legacy_price を返す。"""
    price, legacy = conn.execute(
        "SELECT price, legacy_price FROM orders WHERE id = ?", (order_id,)
    ).fetchone()
    return price if price is not None else legacy
