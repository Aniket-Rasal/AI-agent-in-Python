from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


@dataclass(frozen=True)
class Config:
    base_url: str
    max_documents: int
    interval_minutes: int
    timeout_seconds: int
    request_delay_seconds: float
    max_pages: int
    max_depth: int
    max_pdf_pages: int
    min_text_chars: int
    ocr_provider: str
    aws_region: str | None
    data_dir: Path
    database_path: Path
    log_path: Path
    user_agent: str
    local_pdf_dir: Path | None = None

    @classmethod
    def from_env(cls, project_dir: Path | None = None) -> "Config":
        root = project_dir or Path(__file__).resolve().parents[1]
        _load_dotenv(root / ".env")
        data_dir = Path(os.getenv("DATA_DIR", str(root / "data"))).expanduser()
        max_documents = int(os.getenv("MAX_DOCUMENTS", "100"))
        interval = int(os.getenv("INTERVAL_MINUTES", "30"))
        if max_documents < 1 or interval < 1:
            raise ValueError("MAX_DOCUMENTS and INTERVAL_MINUTES must be positive")
        base_url = os.getenv("MCA_BASE_URL", "https://www.mca.gov.in/").rstrip("/") + "/"
        parts = urlsplit(base_url)
        if parts.scheme != "https" or (parts.hostname or "").lower() not in {"mca.gov.in", "www.mca.gov.in"}:
            raise ValueError("MCA_BASE_URL must use HTTPS on mca.gov.in or www.mca.gov.in")
        return cls(
            base_url=base_url,
            max_documents=max_documents,
            interval_minutes=interval,
            timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20")),
            request_delay_seconds=float(os.getenv("REQUEST_DELAY_SECONDS", "2")),
            max_pages=int(os.getenv("DISCOVERY_MAX_PAGES", "40")),
            max_depth=int(os.getenv("DISCOVERY_MAX_DEPTH", "2")),
            max_pdf_pages=int(os.getenv("OCR_MAX_PDF_PAGES", "100")),
            min_text_chars=int(os.getenv("OCR_MIN_TEXT_CHARS", "80")),
            ocr_provider=os.getenv("OCR_PROVIDER", "tesseract").strip().lower(),
            aws_region=os.getenv("AWS_REGION") or None,
            data_dir=data_dir,
            database_path=Path(os.getenv("DATABASE_PATH", str(data_dir / "metadata" / "documents.sqlite3"))),
            log_path=Path(os.getenv("LOG_PATH", str(data_dir / "logs" / "agent.log"))),
            user_agent=os.getenv("HTTP_USER_AGENT", "MCA-Document-Agent/1.0 (polite public document collector)"),
            local_pdf_dir=Path(os.getenv("LOCAL_PDF_DIR", str(data_dir / "inbox"))).expanduser(),
        )

    @property
    def host(self) -> str:
        from urllib.parse import urlsplit

        return (urlsplit(self.base_url).hostname or "").lower()

    def create_directories(self) -> None:
        for name in ("downloads/raw", "documents", "ocr/text", "metadata", "logs", "state", "inbox", "demo_state"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
        for category in ("Acts", "Notifications", "Circulars", "Rules", "Orders", "Amendments", "Other"):
            (self.data_dir / "documents" / category).mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
