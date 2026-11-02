import unittest

from app.place_order import place_order
from infra.db import OrderStore


class PlaceOrderTest(unittest.TestCase):
    def test_confirms_and_saves(self):
        store = OrderStore()
        order = place_order(store, 'A-1', 'a@example.com', [('pen', 120, 2)])
        self.assertEqual(order.status, 'confirmed')
        self.assertEqual(store.status_of('A-1'), 'confirmed')


if __name__ == '__main__':
    unittest.main()
