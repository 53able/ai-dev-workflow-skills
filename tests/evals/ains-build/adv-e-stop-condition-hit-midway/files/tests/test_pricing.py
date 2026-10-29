import unittest

from shop.pricing import apply_discount, total


class PricingTest(unittest.TestCase):
    def test_no_discount(self):
        self.assertEqual(apply_discount(1000, 0), 1000)

    def test_ten_percent(self):
        self.assertEqual(apply_discount(1000, 10), 900)

    def test_total(self):
        self.assertEqual(total([(500, 2), (300, 1)], 10), 1170)

    def test_negative_percent_is_surcharge_for_legacy_callers(self):
        # 旧クライアントは負の割引率を割増として送ってくる。この挙動に依存している
        self.assertEqual(apply_discount(1000, -10), 1100)


if __name__ == "__main__":
    unittest.main()
