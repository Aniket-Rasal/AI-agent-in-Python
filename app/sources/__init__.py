"""Pluggable sources for public MCA documents and local PDF demonstrations."""

from app.sources.base import DocumentSource
from app.sources.local import LocalDocumentSource
from app.sources.mca import MCADocumentSource

__all__ = ["DocumentSource", "LocalDocumentSource", "MCADocumentSource"]
