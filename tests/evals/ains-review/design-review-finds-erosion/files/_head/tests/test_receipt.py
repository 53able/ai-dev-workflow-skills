import unittest

from app.receipt import build_receipt
from domain.order import Order


class ReceiptTest(unittest.TestCase):
    def test_body_has_required_lines(self):
        order = Order('A-1', 'c-1')
        order.add_item('pen', 250, 2)
        order.add_item('note', 800, 1)
        lines = build_receipt(order, '山田').splitlines()
        self.assertEqual(lines[0], 'サンプル商店')
        self.assertIn('注文番号: A-1', lines)
        self.assertIn('山田 様', lines)
        self.assertIn('pen x2 $5.00', lines)
        self.assertIn('note x1 $8.00', lines)
        self.assertIn('小計 $13.00', lines)
        self.assertIn('消費税 $1.30', lines)
        self.assertIn('合計 $14.30', lines)


if __name__ == '__main__':
    unittest.main()
