import unittest

from app.orders import order_total


class OrdersTest(unittest.TestCase):
    def test_total(self):
        self.assertEqual(order_total(500, 2), 1000)


if __name__ == "__main__":
    unittest.main()
