from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repository:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    source_url TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL DEFAULT 'MCA',
                    title TEXT NOT NULL,
                    document_type TEXT,
                    local_path TEXT,
                    sha256 TEXT,
                    file_size INTEGER,
                    download_status TEXT NOT NULL DEFAULT 'discovered',
                    ocr_status TEXT NOT NULL DEFAULT 'pending',
                    classification_status TEXT NOT NULL DEFAULT 'pending',
                    processing_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_message TEXT,
                    ocr_path TEXT
                )
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(documents)")}
            if "source_kind" not in columns:
                db.execute("ALTER TABLE documents ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'MCA'")
                db.execute("UPDATE documents SET source_kind = 'LOCAL' WHERE source_url LIKE 'local-pdf:%'")
            db.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(download_status, ocr_status, classification_status)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_documents_sha256 ON documents(sha256)")
            db.execute("CREATE TABLE IF NOT EXISTS agent_lock (name TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL)")
            db.execute("""
                CREATE TABLE IF NOT EXISTS agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_kind TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def add_candidate(self, doc_id: str, source_url: str, title: str, source_kind: str = "MCA") -> bool:
        now = utc_now()
        with self.connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO documents(id, source_url, source_kind, title, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, source_url, source_kind, title, now, now),
            )
            return cursor.rowcount == 1

    def update(self, doc_id: str, **fields: Any) -> None:
        allowed = {"document_type", "local_path", "sha256", "file_size", "download_status", "ocr_status", "classification_status", "processing_status", "error_message", "ocr_path", "title"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{column} = ?" for column in values)
        with self.connect() as db:
            db.execute(f"UPDATE documents SET {assignments} WHERE id = ?", (*values.values(), doc_id))

    def get(self, doc_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
            return dict(row) if row else None

    def pending_processing(self) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM documents WHERE download_status = 'success' AND processing_status != 'complete' ORDER BY created_at").fetchall()
            return [dict(row) for row in rows]

    def downloaded_count(self) -> int:
        with self.connect() as db:
            return int(db.execute("SELECT COUNT(DISTINCT sha256) FROM documents WHERE download_status = 'success' AND sha256 IS NOT NULL").fetchone()[0])

    def hash_exists(self, digest: str) -> bool:
        with self.connect() as db:
            return db.execute("SELECT 1 FROM documents WHERE sha256 = ? AND download_status = 'success' LIMIT 1", (digest,)).fetchone() is not None

    def status(self) -> dict[str, int]:
        with self.connect() as db:
            return {
                "downloaded": self.downloaded_count(),
                "ocr_processed": int(db.execute("SELECT COUNT(*) FROM documents WHERE ocr_status = 'success'").fetchone()[0]),
                "classified": int(db.execute("SELECT COUNT(*) FROM documents WHERE classification_status = 'success'").fetchone()[0]),
                "errors": int(db.execute("SELECT COUNT(*) FROM documents WHERE processing_status = 'error' OR download_status = 'failed' OR ocr_status = 'failed'").fetchone()[0]),
                "discovered": int(db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]),
                "discovery_errors": int(db.execute("SELECT COUNT(*) FROM agent_events WHERE event_type = 'discovery_error'").fetchone()[0]),
            }

    def category_counts(self) -> dict[str, int]:
        with self.connect() as db:
            rows = db.execute("SELECT document_type, COUNT(*) AS amount FROM documents WHERE classification_status = 'success' GROUP BY document_type").fetchall()
            return {str(row[0] or "Other"): int(row[1]) for row in rows}

    def record_event(self, source_kind: str, event_type: str, message: str) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO agent_events(source_kind, event_type, message, created_at) VALUES (?, ?, ?, ?)",
                (source_kind, event_type, message[:1000], utc_now()),
            )

    def acquire_lease(self, owner: str, ttl_seconds: int = 3600) -> bool:
        import time

        now = time.time()
        with self.connect() as db:
            db.execute("DELETE FROM agent_lock WHERE expires_at <= ?", (now,))
            try:
                db.execute("INSERT INTO agent_lock(name, owner, expires_at) VALUES ('cycle', ?, ?)", (owner, now + ttl_seconds))
                return True
            except sqlite3.IntegrityError:
                return False

    def release_lease(self, owner: str) -> None:
        with self.connect() as db:
            db.execute("DELETE FROM agent_lock WHERE name = 'cycle' AND owner = ?", (owner,))

    def renew_lease(self, owner: str, ttl_seconds: int = 3600) -> bool:
        import time

        with self.connect() as db:
            cursor = db.execute("UPDATE agent_lock SET expires_at = ? WHERE name = 'cycle' AND owner = ?", (time.time() + ttl_seconds, owner))
            return cursor.rowcount == 1
