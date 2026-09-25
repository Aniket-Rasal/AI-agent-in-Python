from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Classification:
    category: str
    rule_score: float
    rationale: str


class DocumentClassifier:
    """Rule-based filing labels; rule_score is a heuristic, not ML confidence."""
    RULES = (
        ("Amendments", (r"\bamendments?\b", r"\bamendment rules\b")),
        ("Notifications", (r"\bnotifications?\b", r"\bg\.s\.r\.?\s*\d", r"\bs\.o\.?\s*\d")),
        ("Circulars", (r"\bcirculars?\b",)),
        ("Orders", (r"\border(?:s)?\b", r"\btribunal order\b")),
        ("Rules", (r"\brules\b", r"\b(rule|rules)\s*,?\s*20\d{2}\b")),
        ("Acts", (r"\bact no\.?\s*\d+\s+of\s+20\d{2}\b", r"\bcompanies act\s*,?\s*2013\b")),
    )

    def classify(self, title: str, text: str) -> Classification:
        title_text = title.casefold()
        body = text[:250_000].casefold()
        for category, patterns in self.RULES:
            title_hits = sum(bool(re.search(pattern, title_text, re.I)) for pattern in patterns)
            if title_hits:
                return Classification(category, 0.95, f"Matched {category.lower()} indicator in title")
        for category, patterns in self.RULES:
            if any(re.search(pattern, body, re.I) for pattern in patterns):
                return Classification(category, 0.75, f"Matched {category.lower()} indicator in document text")
        return Classification("Other", 0.35, "No strong category indicator found")
