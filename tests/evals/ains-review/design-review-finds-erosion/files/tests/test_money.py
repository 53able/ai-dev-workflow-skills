import unittest

from domain import money


class MoneyTest(unittest.TestCase):
    def test_tax_truncates(self):
        self.assertEqual(money.tax(1000), 100)
        self.assertEqual(money.tax(1009), 100)

    def test_format(self):
        self.assertEqual(money.format_usd(1234), '$12.34')
        self.assertEqual(money.format_usd(5), '$0.05')


if __name__ == '__main__':
    unittest.main()
