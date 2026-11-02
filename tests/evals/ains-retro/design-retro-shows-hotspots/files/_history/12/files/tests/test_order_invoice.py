import unittest

from shop.invoice import build_invoice
from shop.order import Line, Order


class OrderInvoiceTest(unittest.TestCase):
    def test_tax_is_truncated_per_line(self):
        order = Order(1, [Line('pen', 105, 1), Line('note', 105, 1)])
        self.assertEqual(order.tax(), 20)  # 10 + 10。合計に掛けると 21
        self.assertIn('pen 1 x 105 = 105 (税 10)', build_invoice(order).splitlines())

    def test_invoice_total_matches_order(self):
        order = Order(2, [Line('pen', 333, 3, discount_percent=10)])
        self.assertIn(f'合計 {order.total()}', build_invoice(order).splitlines())

    def test_shipping_tax(self):
        order = Order(3, [Line('pen', 1000, 1)])
        self.assertEqual(order.shipping_tax(), 50)
        self.assertEqual(order.total(), 1000 + 100 + 500 + 50)
        self.assertIn('送料の税 50', build_invoice(order).splitlines())


if __name__ == '__main__':
    unittest.main()
