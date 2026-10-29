import unittest

from shop.shipping import shipping_fee


class ShippingTest(unittest.TestCase):
    def test_under_threshold_pays_fee(self):
        self.assertEqual(shipping_fee(4999), 500)

    def test_exactly_threshold_is_free(self):
        self.assertEqual(shipping_fee(5000), 0)


if __name__ == "__main__":
    unittest.main()
