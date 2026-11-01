import unittest

from domain.order import Order, OrderError


class OrderTest(unittest.TestCase):
    def test_total(self):
        order = Order('A-1', 'a@example.com', [('pen', 120, 2), ('note', 300, 1)])
        self.assertEqual(order.total(), 540)

    def test_confirm(self):
        order = Order('A-1', 'a@example.com', [('pen', 120, 1)])
        order.confirm()
        self.assertEqual(order.status, 'confirmed')

    def test_confirm_rejects_empty_and_twice(self):
        with self.assertRaises(OrderError):
            Order('A-2', 'a@example.com', []).confirm()
        order = Order('A-3', 'a@example.com', [('pen', 120, 1)])
        order.confirm()
        with self.assertRaises(OrderError):
            order.confirm()


if __name__ == '__main__':
    unittest.main()
