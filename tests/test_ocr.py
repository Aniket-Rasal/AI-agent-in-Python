import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pymupdf

from app.ocr.tesseract_provider import TesseractOCRProvider
from app.ocr.textract_provider import AWSTextractOCRProvider


class OCRProviderTests(unittest.TestCase):
    def _pdf(self, path: Path, with_text: bool) -> None:
        document = pymupdf.open()
        page = document.new_page()
        if with_text:
            page.insert_text((72, 72), "Embedded Companies Act document text for OCR testing.")
        else:
            page.draw_rect(pymupdf.Rect(40, 40, 500, 700), color=(0, 0, 0))
        document.save(path)
        document.close()

    def test_uses_embedded_pdf_text_when_it_is_sufficient(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "text.pdf"
            self._pdf(path, with_text=True)
            with patch("pytesseract.image_to_string") as ocr:
                result = TesseractOCRProvider(min_text_chars=10).extract_text(path)
            self.assertIn("Embedded Companies Act", result)
            ocr.assert_not_called()

    def test_uses_tesseract_when_page_has_no_embedded_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scan.pdf"
            self._pdf(path, with_text=False)
            with patch("pytesseract.image_to_string", return_value="recognized scanned text") as ocr:
                result = TesseractOCRProvider(min_text_chars=80, max_pages=1).extract_text(path)
            self.assertEqual(result, "recognized scanned text")
            ocr.assert_called_once()

    def test_textract_provider_uses_configured_region_and_returns_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "page.pdf"
            self._pdf(path, with_text=False)
            client = Mock()
            client.detect_document_text.return_value = {"Blocks": [{"BlockType": "LINE", "Text": "Textract result"}]}
            boto3 = types.SimpleNamespace(client=lambda service, region_name: client)
            with patch.dict(sys.modules, {"boto3": boto3}):
                result = AWSTextractOCRProvider(region="ap-south-1", max_pages=1).extract_text(path)
            self.assertEqual(result, "Textract result")
            self.assertEqual(client.detect_document_text.call_count, 1)
