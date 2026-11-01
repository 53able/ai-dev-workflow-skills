"""注文の保存先（SQLite）。"""
import sqlite3


class OrderStore:
    def __init__(self, path: str = ':memory:'):
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            'CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, buyer_email TEXT, total INTEGER, status TEXT)')

    def save(self, order) -> None:
        self.conn.execute(
            'INSERT OR REPLACE INTO orders VALUES (?, ?, ?, ?)',
            (order.order_id, order.buyer_email, order.total(), order.status))
        self.conn.commit()

    def status_of(self, order_id: str) -> str | None:
        row = self.conn.execute('SELECT status FROM orders WHERE order_id = ?', (order_id,)).fetchone()
        return row[0] if row else None
