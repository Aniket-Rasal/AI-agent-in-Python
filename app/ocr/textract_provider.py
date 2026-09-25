from __future__ import annotations

from pathlib import Path

from app.ocr.base import OCRProvider


class AWSTextractOCRProvider(OCRProvider):
    def __init__(self, region: str | None = None, max_pages: int = 100, dpi: int = 180):
        self.region = region
        self.max_pages = max_pages
        self.dpi = dpi

    def extract_text(self, pdf_path: Path) -> str:
        try:
            import boto3
            import pymupdf as fitz
        except ImportError as exc:
            raise RuntimeError("Install boto3 and PyMuPDF to use AWS Textract") from exc
        client = boto3.client("textract", region_name=self.region)
        lines: list[str] = []
        with fitz.open(pdf_path) as document:
            scale = self.dpi / 72
            for page in list(document)[: self.max_pages]:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                result = client.detect_document_text(Document={"Bytes": pixmap.tobytes("png")})
                lines.extend(block["Text"] for block in result.get("Blocks", []) if block.get("BlockType") == "LINE" and "Text" in block)
        return "\n".join(lines).strip()
