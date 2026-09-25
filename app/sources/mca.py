from __future__ import annotations

from pathlib import Path

from app.config import Config
from app.discovery.mca_discovery import MCADiscovery
from app.discovery.mca_web_portal import MCAWebPortal
from app.downloader.document_downloader import DocumentDownloader
from app.models import Candidate
from app.sources.base import DocumentSource


class MCADocumentSource(DocumentSource):
    """Uses MCA public pages and links without authentication or access bypasses."""

    name = "MCA"

    def __init__(self, config: Config):
        self.portal = MCAWebPortal(config)
        self.discovery = MCADiscovery(config, portal=self.portal)
        self.downloader = DocumentDownloader(config, portal=self.portal)

    def discover(self) -> list[Candidate]:
        try:
            return self.discovery.discover()
        except Exception as exc:
            message = str(exc)
            if "403" in message:
                raise RuntimeError("MCA document discovery unavailable: HTTP 403") from exc
            raise RuntimeError(f"MCA document discovery unavailable: {message}") from exc

    def download(self, candidate: Candidate, destination: Path) -> tuple[str, int]:
        return self.downloader.download(candidate.source_url, destination)

    def close(self) -> None:
        self.portal.close()
