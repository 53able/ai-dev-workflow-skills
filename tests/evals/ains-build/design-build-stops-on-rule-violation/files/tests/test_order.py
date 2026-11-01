import unittest

from domain.order import Order, OrderError


class OrderTest(unittest.TestCase):
    def test_confirm(self):
        order = Order('A-1', [('pen', 2)])
        order.confirm()
        self.assertEqual(order.status, 'confirmed')

    def test_confirm_rejects_invalid(self):
        with self.assertRaises(OrderError):
            Order('A-2', []).confirm()
        with self.assertRaises(OrderError):
            Order('A-3', [('pen', 0)]).confirm()
        order = Order('A-4', [('pen', 1)])
        order.confirm()
        with self.assertRaises(OrderError):
            order.confirm()


if __name__ == '__main__':
    unittest.main()
