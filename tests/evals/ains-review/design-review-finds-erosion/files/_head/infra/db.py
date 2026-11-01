"""保存先（SQLite）。"""
import sqlite3


class Database:
    def __init__(self, path: str = ':memory:'):
        self.conn = sqlite3.connect(path)
        self.conn.execute('CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT, amount INTEGER)')
        self.conn.execute('CREATE TABLE IF NOT EXISTS receipts (order_id TEXT PRIMARY KEY, body TEXT)')

    def save_order(self, order_id: str, customer_id: str, amount: int) -> None:
        self.conn.execute('INSERT OR REPLACE INTO orders VALUES (?, ?, ?)', (order_id, customer_id, amount))
        self.conn.commit()

    def amount_of(self, order_id: str) -> int | None:
        row = self.conn.execute('SELECT amount FROM orders WHERE order_id = ?', (order_id,)).fetchone()
        return row[0] if row else None

    def save_receipt(self, order_id: str, body: str) -> None:
        self.conn.execute('INSERT OR REPLACE INTO receipts VALUES (?, ?)', (order_id, body))
        self.conn.commit()

    def receipt_of(self, order_id: str) -> str | None:
        row = self.conn.execute('SELECT body FROM receipts WHERE order_id = ?', (order_id,)).fetchone()
        return row[0] if row else None
