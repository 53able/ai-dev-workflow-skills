import unittest

from app.receipt import build_receipt
from domain.order import Order


class ReceiptTest(unittest.TestCase):
    def test_body_has_required_lines(self):
        order = Order('A-1', 'c-1')
        order.add_item('pen', 250, 2)
        order.add_item('note', 800, 1)
        text = build_receipt(order, '山田')
        lines = text.splitlines()
        self.assertEqual(lines[0], 'サンプル商店')
        self.assertIn('注文番号: A-1', lines)
        self.assertIn('山田 様', lines)
        self.assertIn('note x1 800円', lines)
        self.assertIn('pen x2 500円', lines)
        self.assertTrue(any(line.startswith('小計 ') for line in lines))
        self.assertTrue(any(line.startswith('消費税 ') for line in lines))
        self.assertTrue(any(line.startswith('合計 ') for line in lines))


if __name__ == '__main__':
    unittest.main()
