import unittest

from app.checkout import checkout
from domain import money
from domain.order import Order
from infra.db import Database


class CheckoutTest(unittest.TestCase):
    def test_amount_includes_tax_and_is_saved(self):
        db = Database()
        order = Order('A-1', 'c-1')
        order.add_item('pen', 250, 4)
        amount, _ = checkout(db, order, '山田')
        self.assertEqual(amount, 1100)
        self.assertEqual(db.amount_of('A-1'), 1100)

    def test_receipt_is_returned_and_saved(self):
        db = Database()
        order = Order('A-2', 'c-1')
        order.add_item('pen', 250, 2)
        _, text = checkout(db, order, '山田')
        self.assertIn('注文番号: A-2', text)
        self.assertEqual(db.receipt_of('A-2'), text)

    def test_receipt_total_matches_amount(self):
        db = Database()
        order = Order('A-3', 'c-1')
        order.add_item('pen', 255, 3)
        order.add_item('note', 799, 1)
        amount, text = checkout(db, order, '山田')
        self.assertIn(f'合計 {money.format_usd(amount)}', text.splitlines())


if __name__ == '__main__':
    unittest.main()
