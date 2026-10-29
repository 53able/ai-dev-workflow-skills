import os
import tempfile
import unittest
from pathlib import Path

from app import settings


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings.DATA_DIR = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_reload(self):
        settings.save("u1", "u1", {"language": "en"})
        self.assertEqual(settings.load("u1")["language"], "en")

    def test_cannot_save_other_user(self):
        with self.assertRaises(settings.PermissionDenied):
            settings.save("u1", "u2", {"language": "en"})


if __name__ == "__main__":
    unittest.main()
