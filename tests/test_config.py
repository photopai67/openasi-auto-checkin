import os
import tempfile
import unittest
from pathlib import Path

from openasi_checkin.config import load_env_file


class ConfigTests(unittest.TestCase):
    def test_loads_values_without_overwriting_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("OPENASI_EMAIL=file@example.com\nQUOTED=\"value\"\n", encoding="utf-8")
            os.environ["OPENASI_EMAIL"] = "existing@example.com"
            try:
                load_env_file(path)
                self.assertEqual(os.environ["OPENASI_EMAIL"], "existing@example.com")
                self.assertEqual(os.environ["QUOTED"], "value")
            finally:
                os.environ.pop("OPENASI_EMAIL", None)
                os.environ.pop("QUOTED", None)

