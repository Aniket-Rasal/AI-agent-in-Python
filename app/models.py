from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Candidate:
    source_url: str
    title: str
    discovered_at: str
