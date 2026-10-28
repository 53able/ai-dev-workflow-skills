import unittest

from app.points import balance


class PointsTest(unittest.TestCase):
    def test_balance(self):
        self.assertEqual(balance({"points": 10}), 10)


if __name__ == "__main__":
    unittest.main()
