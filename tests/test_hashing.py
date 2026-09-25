import tempfile
import unittest
from pathlib import Path

from app.utils import safe_stem, sha256_file


class HashTests(unittest.TestCase):
    def test_sha256_is_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "a.bin"
            path.write_bytes(b"example")
            self.assertEqual(sha256_file(path), sha256_file(path))
            self.assertEqual(sha256_file(path), "50d858e0985ecc7f60418aaf0cc5ab587f42c2570a884095a9e8ccacd0f6545c")

    def test_filename_is_sanitized(self):
        self.assertNotIn("/", safe_stem("../../bad/name"))
