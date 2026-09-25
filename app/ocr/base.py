from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class OCRProvider(ABC):
    @abstractmethod
    def extract_text(self, pdf_path: Path) -> str:
        """Return text extracted from a PDF, using OCR where needed."""


def create_provider(name: str, region: str | None = None, min_text_chars: int = 80, max_pages: int = 100) -> OCRProvider:
    if name == "tesseract":
        from app.ocr.tesseract_provider import TesseractOCRProvider

        return TesseractOCRProvider(min_text_chars=min_text_chars, max_pages=max_pages)
    if name == "textract":
        from app.ocr.textract_provider import AWSTextractOCRProvider

        return AWSTextractOCRProvider(region=region, max_pages=max_pages)
    raise ValueError(f"Unsupported OCR_PROVIDER: {name}")
