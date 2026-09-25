from __future__ import annotations

from io import BytesIO
from pathlib import Path

from app.config import Config
from app.ocr.base import OCRProvider


class TesseractOCRProvider(OCRProvider):
    def __init__(self, min_text_chars: int = 80, max_pages: int = 100, dpi: int = 180, language: str = "eng"):
        self.min_text_chars = min_text_chars
        self.max_pages = max_pages
        self.dpi = dpi
        self.language = language

    def extract_text(self, pdf_path: Path) -> str:
        try:
            import pymupdf as fitz
        except ImportError as exc:
            raise RuntimeError("Install PyMuPDF to extract PDF text") from exc

        with fitz.open(pdf_path) as document:
            pages = list(document)[: self.max_pages]
            embedded = [page.get_text("text").strip() for page in pages]
            if sum(len(text) for text in embedded) >= self.min_text_chars:
                return "\n\n".join(embedded).strip()
            try:
                import pytesseract
            except ImportError as exc:
                if any(embedded):
                    return "\n\n".join(embedded).strip()
                raise RuntimeError("Install pytesseract and the Tesseract executable for scanned PDFs") from exc

            extracted: list[str] = []
            scale = self.dpi / 72
            for page, text in zip(pages, embedded):
                if len(text) >= 20:
                    extracted.append(text)
                    continue
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                png = pixmap.tobytes("png")
                image = __import__("PIL.Image", fromlist=["Image"]).open(BytesIO(png))
                extracted.append(pytesseract.image_to_string(image, lang=self.language).strip())
            return "\n\n".join(extracted).strip()
