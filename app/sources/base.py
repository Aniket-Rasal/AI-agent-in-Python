from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models import Candidate


class DocumentSource(ABC):
    """Discovers documents and stages their bytes for the shared pipeline."""

    name = "SOURCE"

    @abstractmethod
    def discover(self) -> list[Candidate]:
        raise NotImplementedError

    @abstractmethod
    def download(self, candidate: Candidate, destination: Path) -> tuple[str, int]:
        raise NotImplementedError

    def close(self) -> None:
        """Release source resources, if any."""
