import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Config
from app.ocr.base import create_provider


class ConfigTests(unittest.TestCase):
    def test_scheduler_defaults_to_30_minutes(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Config.from_env(Path(directory)).interval_minutes, 30)

    def test_scheduler_interval_is_configurable(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"INTERVAL_MINUTES": "1"}, clear=True):
            self.assertEqual(Config.from_env(Path(directory)).interval_minutes, 1)

    def test_ocr_provider_selection(self):
        self.assertEqual(type(create_provider("tesseract")).__name__, "TesseractOCRProvider")
        with self.assertRaises(ValueError):
            create_provider("unknown")

    def test_rejects_nonpositive_limit(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"MAX_DOCUMENTS": "0"}, clear=True):
            with self.assertRaises(ValueError):
                Config.from_env(Path(directory))

    def test_rejects_non_mca_base_url(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"MCA_BASE_URL": "https://example.com/"}, clear=True):
            with self.assertRaises(ValueError):
                Config.from_env(Path(directory))
