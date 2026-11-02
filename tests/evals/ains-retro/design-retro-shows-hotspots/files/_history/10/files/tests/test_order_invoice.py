import unittest

from shop.invoice import build_invoice
from shop.order import Line, Order


class OrderInvoiceTest(unittest.TestCase):
    def test_tax_is_truncated_per_line(self):
        order = Order(1, [Line('pen', 105, 1), Line('note', 105, 1)])
        self.assertEqual(order.tax(), 20)  # 10 + 10。合計に掛けると 21
        self.assertIn('pen 1 x 105 = 105 (税 10)', build_invoice(order).splitlines())


if __name__ == '__main__':
    unittest.main()
