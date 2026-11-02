import unittest

from shop.cart import Cart


class CartTest(unittest.TestCase):
    def test_add_and_remove(self):
        cart = Cart()
        cart.add('pen', 2)
        cart.add('pen')
        self.assertEqual(cart.items, {'pen': 3})
        cart.remove('pen')
        self.assertEqual(cart.items, {})


if __name__ == '__main__':
    unittest.main()
