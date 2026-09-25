from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from app.config import Config
from app.downloader.document_downloader import DocumentDownloader
from app.models import Candidate
from app.sources.base import DocumentSource
from app.utils import sha256_file


class LocalDocumentSource(DocumentSource):
    """Reads PDFs from a local folder without presenting them as MCA downloads."""

    name = "LOCAL"

    def __init__(self, config: Config, directory: Path | None = None, files: list[Path] | None = None):
        self.directory = Path(directory or config.local_pdf_dir or config.data_dir / "inbox").expanduser()
        self.files = [Path(item).expanduser() for item in files] if files is not None else None
        self.downloader = DocumentDownloader(config)
        self._paths: dict[str, Path] = {}

    def discover(self) -> list[Candidate]:
        paths = self.files if self.files is not None else sorted(
            (item for item in self.directory.iterdir() if item.is_file() and item.suffix.lower() == ".pdf"),
            key=lambda item: item.name.casefold(),
        ) if self.directory.is_dir() else []
        discovered_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        candidates: list[Candidate] = []
        self._paths.clear()
        for path in paths:
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            digest = sha256_file(path)
            source_url = f"local-pdf://sha256/{digest}"
            self._paths[source_url] = path
            candidates.append(Candidate(source_url, path.stem[:300], discovered_at))
        return candidates

    def download(self, candidate: Candidate, destination: Path) -> tuple[str, int]:
        source_path = self._paths.get(candidate.source_url)
        if source_path is None:
            raise FileNotFoundError("Local PDF candidate expired; run discovery again")
        return self.downloader.import_local_pdf(source_path, destination)
