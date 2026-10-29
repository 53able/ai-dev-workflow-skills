import sqlite3
import unittest

from shop.orders import order_price


class OrderPriceTest(unittest.TestCase):
    def test_falls_back_to_legacy_price(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, price INTEGER, legacy_price INTEGER)")
        conn.execute("INSERT INTO orders VALUES (1, NULL, 700)")
        self.assertEqual(order_price(conn, 1), 700)


if __name__ == "__main__":
    unittest.main()
