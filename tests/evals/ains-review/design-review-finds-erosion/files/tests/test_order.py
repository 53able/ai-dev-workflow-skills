import unittest

from domain.order import Order, OrderError


class OrderTest(unittest.TestCase):
    def test_total(self):
        order = Order('A-1', 'c-1')
        order.add_item('pen', 250, 2)
        order.add_item('note', 500, 1)
        self.assertEqual(order.total(), 1000)

    def test_rejects_zero_qty(self):
        with self.assertRaises(OrderError):
            Order('A-1', 'c-1').add_item('pen', 250, 0)


if __name__ == '__main__':
    unittest.main()
