import unittest

from app.checkout import checkout
from domain.order import Order
from infra.db import Database


class CheckoutTest(unittest.TestCase):
    def test_amount_includes_tax_and_is_saved(self):
        db = Database()
        order = Order('A-1', 'c-1')
        order.add_item('pen', 250, 4)
        self.assertEqual(checkout(db, order), 1100)
        self.assertEqual(db.amount_of('A-1'), 1100)


if __name__ == '__main__':
    unittest.main()
