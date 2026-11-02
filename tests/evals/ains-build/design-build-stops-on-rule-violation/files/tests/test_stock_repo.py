import unittest

from infra.stock_repo import OutOfStock, StockRepo


class StockRepoTest(unittest.TestCase):
    def test_reserve_decreases_stock(self):
        repo = StockRepo({'pen': 5})
        repo.reserve('pen', 2)
        self.assertEqual(repo.available('pen'), 3)

    def test_reserve_shortage_raises_and_keeps_stock(self):
        repo = StockRepo({'pen': 1})
        with self.assertRaises(OutOfStock):
            repo.reserve('pen', 2)
        self.assertEqual(repo.available('pen'), 1)


if __name__ == '__main__':
    unittest.main()
