import unittest

from shop.pricing import apply_discount, total


class PricingTest(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(apply_discount(1000, 0), 1000)

    def test_ten_percent(self):
        self.assertEqual(apply_discount(1000, 10), 900)

    def test_total(self):
        self.assertEqual(total([(500, 2), (300, 1)], 10), 1170)

    def test_full_and_over_discount_is_zero(self):
        self.assertEqual(apply_discount(1000, 100), 0)
        self.assertEqual(apply_discount(1000, 150), 0)


if __name__ == "__main__":
    unittest.main()
