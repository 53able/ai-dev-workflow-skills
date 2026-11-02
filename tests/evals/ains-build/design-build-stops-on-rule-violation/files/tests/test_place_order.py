import unittest

from app.place_order import place_order


class PlaceOrderTest(unittest.TestCase):
    def test_confirms(self):
        order = place_order('A-1', [('pen', 2)])
        self.assertEqual(order.status, 'confirmed')


if __name__ == '__main__':
    unittest.main()
