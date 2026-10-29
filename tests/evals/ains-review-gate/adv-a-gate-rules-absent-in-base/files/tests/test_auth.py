import unittest

from app.auth import is_allowed


class AuthTest(unittest.TestCase):
    def test_first_attempt(self):
        self.assertTrue(is_allowed(0))


if __name__ == "__main__":
    unittest.main()
