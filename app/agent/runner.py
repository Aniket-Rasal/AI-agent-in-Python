from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from app.classifier.document_classifier import DocumentClassifier
from app.config import Config
from app.database.repository import Repository
from app.discovery.mca_discovery import MCADiscovery, is_relevant
from app.discovery.mca_web_portal import MCAWebPortal
from app.downloader.document_downloader import DocumentDownloader
from app.models import Candidate
from app.ocr.base import create_provider
from app.sources.base import DocumentSource
from app.utils import safe_stem

LOG = logging.getLogger(__name__)


class AgentRunner:
    def __init__(self, config: Config, repository: Repository | None = None, discovery: MCADiscovery | None = None, downloader: DocumentDownloader | None = None, ocr_provider=None, classifier: DocumentClassifier | None = None, source: DocumentSource | None = None):
        self.config = config
        self.config.create_directories()
        self.repository = repository or Repository(config.database_path)
        self.source = source
        self.portal = MCAWebPortal(config) if source is None and discovery is None and downloader is None else None
        self.discovery = discovery or (MCADiscovery(config, portal=self.portal) if source is None else None)
        self.downloader = downloader or (DocumentDownloader(config, portal=self.portal) if source is None else None)
        self.ocr_provider = ocr_provider or create_provider(config.ocr_provider, config.aws_region, config.min_text_chars, config.max_pdf_pages)
        self.classifier = classifier or DocumentClassifier()
        self.last_discovered = 0

    def run_once(self, owner: str | None = None, process_existing_only: bool = False, source: DocumentSource | None = None) -> str:
        active_source = source or self.source
        owner = owner or str(uuid.uuid4())
        if not self.repository.acquire_lease(owner):
            LOG.warning("Another agent cycle owns the database lease; skipping this cycle")
            if active_source is not None:
                active_source.close()
            return "locked"
        self.last_discovered = 0
        heartbeat_stop = threading.Event()

        def heartbeat() -> None:
            while not heartbeat_stop.wait(300):
                if not self.repository.renew_lease(owner):
                    LOG.error("Agent cycle lease was lost")
                    return

        heartbeat_thread = threading.Thread(target=heartbeat, name="mca-lease-heartbeat", daemon=True)
        heartbeat_thread.start()
        try:
            count = self.repository.downloaded_count()
            LOG.info("Agent cycle started; successful unique downloads=%d/%d", count, self.config.max_documents)
            self._resume_pending()
            count = self.repository.downloaded_count()
            if count >= self.config.max_documents:
                LOG.info("Agent stopped at MAX_DOCUMENTS=%d", self.config.max_documents)
                return "limit"
            if process_existing_only:
                return "complete"
            try:
                candidates = active_source.discover() if active_source is not None else self.discovery.discover()
            except Exception as exc:
                LOG.error("%s", str(exc))
                self.repository.record_event(active_source.name if active_source else "MCA", "discovery_error", str(exc))
                return "unavailable"
            self.last_discovered = len(candidates)
            LOG.info("Discovered %d candidate(s)", len(candidates))
            for candidate in candidates:
                if self.repository.downloaded_count() >= self.config.max_documents:
                    LOG.info("Agent stopped at MAX_DOCUMENTS=%d", self.config.max_documents)
                    return "limit"
                self._handle_candidate(candidate, active_source)
            return "complete"
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1)
            self.repository.release_lease(owner)
            if active_source is not None:
                active_source.close()
            elif self.portal is not None:
                self.portal.close()

    def import_local_pdf(self, source: Path, title: str | None = None) -> str:
        """Import a user-downloaded PDF into the same durable processing pipeline."""
        owner = str(uuid.uuid4())
        if not self.repository.acquire_lease(owner):
            LOG.warning("Another agent cycle owns the database lease; skipping local PDF import")
            return "locked"
        staging: Path | None = None
        try:
            if self.repository.downloaded_count() >= self.config.max_documents:
                LOG.info("Agent stopped at MAX_DOCUMENTS=%d", self.config.max_documents)
                return "limit"

            source = Path(source).expanduser()
            display_title = (title or source.stem).strip() or source.name
            staging = self.config.data_dir / "downloads" / "raw" / f".local-{uuid.uuid4().hex}.part.pdf"
            LOG.info("Importing local PDF: %s", display_title)
            digest, size = self.downloader.import_local_pdf(source, staging)

            source_url = f"local-pdf://sha256/{digest}"
            doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source_url))
            self.repository.add_candidate(doc_id, source_url, display_title, source_kind="LOCAL")
            row = self.repository.get(doc_id)
            if row and row["download_status"] in ("success", "duplicate"):
                staging.unlink(missing_ok=True)
                LOG.info("Local PDF already imported: %s", display_title)
                return "duplicate"

            if self.repository.hash_exists(digest):
                staging.unlink(missing_ok=True)
                self.repository.update(doc_id, download_status="duplicate", sha256=digest, file_size=size, processing_status="complete", error_message="Identical SHA-256 already recorded")
                LOG.info("Local PDF duplicates previously recorded content: %s", display_title)
                return "duplicate"

            final_path = self.config.data_dir / "downloads" / "raw" / f"{digest}.pdf"
            if final_path.exists():
                staging.unlink(missing_ok=True)
            else:
                os.replace(staging, final_path)
            staging = None
            self.repository.update(doc_id, download_status="success", sha256=digest, file_size=size, local_path=str(final_path), processing_status="pending", error_message=None)
            LOG.info("Local PDF imported: %s (%d bytes)", display_title, size)
            try:
                self._process_document(doc_id)
            except Exception as exc:
                LOG.exception("Post-import processing failed for %s", display_title)
                self.repository.update(doc_id, processing_status="error", error_message=str(exc)[:1000])
                return "failed"
            return "complete"
        except Exception as exc:
            LOG.exception("Local PDF import failed")
            return "failed"
        finally:
            if staging:
                staging.unlink(missing_ok=True)
            self.repository.release_lease(owner)

    def import_local_directory(self, directory: Path) -> str:
        """Import PDF files from a folder until the configured unique-document cap is reached."""
        directory = Path(directory).expanduser()
        if not directory.is_dir():
            LOG.error("PDF import folder does not exist: %s", directory)
            return "failed"
        files = sorted((path for path in directory.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"), key=lambda path: path.name.casefold())
        if not files:
            LOG.warning("No PDF files found in import folder: %s", directory)
            return "complete"

        completed = 0
        failed = 0
        for source in files:
            if self.repository.downloaded_count() >= self.config.max_documents:
                LOG.info("Agent stopped at MAX_DOCUMENTS=%d", self.config.max_documents)
                break
            outcome = self.import_local_pdf(source)
            if outcome == "locked":
                return "locked"
            if outcome == "failed":
                failed += 1
            else:
                completed += 1
        LOG.info("Folder import finished: processed=%d failed=%d", completed, failed)
        return "failed" if failed and completed == 0 else "complete"

    def _handle_candidate(self, candidate: Candidate, source: DocumentSource | None = None) -> None:
        if source is None or source.name == "MCA":
            relevant = is_relevant(f"{candidate.title} {candidate.source_url}")
        else:
            relevant = True
        if not relevant:
            LOG.info("Skipping candidate without Companies Act relevance: %s", candidate.title)
            return
        doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, candidate.source_url))
        self.repository.add_candidate(doc_id, candidate.source_url, candidate.title, source_kind=source.name if source else "MCA")
        row = self.repository.get(doc_id)
        if row and row["download_status"] in ("success", "duplicate"):
            LOG.info("Already downloaded: %s", candidate.title)
            return
        raw_dir = self.config.data_dir / "downloads" / "raw"
        staging = raw_dir / f".{doc_id}.part.pdf"
        try:
            LOG.info("Downloading document: %s", candidate.title)
            if self.config.request_delay_seconds > 0:
                time.sleep(self.config.request_delay_seconds)
            digest, size = source.download(candidate, staging) if source else self.downloader.download(candidate.source_url, staging)
        except Exception as exc:
            staging.unlink(missing_ok=True)
            LOG.exception("Download failed for %s", candidate.title)
            self.repository.update(doc_id, download_status="failed", processing_status="error", error_message=str(exc)[:1000])
            return

        if self.repository.hash_exists(digest):
            staging.unlink(missing_ok=True)
            self.repository.update(doc_id, download_status="duplicate", sha256=digest, file_size=size, processing_status="complete", error_message="Identical SHA-256 already recorded")
            LOG.info("Duplicate content skipped: %s", candidate.title)
            return
        final_path = raw_dir / f"{digest}.pdf"
        try:
            if final_path.exists():
                staging.unlink(missing_ok=True)
            else:
                os.replace(staging, final_path)
            self.repository.update(doc_id, download_status="success", sha256=digest, file_size=size, local_path=str(final_path), processing_status="pending", error_message=None)
            LOG.info("Download succeeded: %s (%d bytes)", candidate.title, size)
        except Exception as exc:
            staging.unlink(missing_ok=True)
            LOG.exception("Could not publish validated download for %s", candidate.title)
            self.repository.update(doc_id, download_status="failed", processing_status="error", error_message=str(exc)[:1000])
            return
        try:
            self._process_document(doc_id)
        except Exception as exc:
            LOG.exception("Post-download processing failed for %s", candidate.title)
            self.repository.update(doc_id, processing_status="error", error_message=str(exc)[:1000])

    def _resume_pending(self) -> None:
        pending = self.repository.pending_processing()
        if pending:
            LOG.info("Resuming %d pending document(s)", len(pending))
        for row in pending:
            try:
                if not row.get("local_path") or not Path(row["local_path"]).is_file():
                    raise FileNotFoundError("Recorded PDF is missing")
                self._process_document(row["id"])
            except Exception as exc:
                LOG.exception("Resume failed for document %s", row["id"])
                self.repository.update(row["id"], processing_status="error", error_message=str(exc)[:1000])

    def _process_document(self, doc_id: str) -> None:
        row = self.repository.get(doc_id)
        if not row or not row.get("local_path"):
            raise RuntimeError("Downloaded document has no local path")
        pdf_path = Path(row["local_path"])
        ocr_succeeded = False
        try:
            LOG.info("OCR started: %s", row["title"])
            text = self.ocr_provider.extract_text(pdf_path)
            if not text.strip():
                raise RuntimeError("OCR/text extraction returned empty text")
            text_path = self.config.data_dir / "ocr" / "text" / f"{doc_id}.txt"
            text_path.parent.mkdir(parents=True, exist_ok=True)
            temp_text = text_path.with_suffix(".tmp")
            temp_text.write_text(text, encoding="utf-8")
            os.replace(temp_text, text_path)
            self.repository.update(doc_id, ocr_status="success", ocr_path=str(text_path), error_message=None)
            ocr_succeeded = True
            LOG.info("OCR completed: %s", row["title"])
        except Exception as exc:
            text = ""
            self.repository.update(doc_id, ocr_status="failed", error_message=f"OCR: {exc}"[:1000])
            LOG.exception("OCR failed: %s", row["title"])

        classification = self.classifier.classify(row["title"], text)
        safe_title = safe_stem(row["title"])
        category_path = self.config.data_dir / "documents" / classification.category / f"{safe_title}-{doc_id[:8]}.pdf"
        category_path.parent.mkdir(parents=True, exist_ok=True)
        if not category_path.exists():
            shutil.copy2(pdf_path, category_path)
        status = self.repository.get(doc_id)
        error = status.get("error_message")
        self.repository.update(doc_id, document_type=classification.category, classification_status="success", processing_status="complete" if ocr_succeeded else "error", error_message=error)
        LOG.info("Classified %s as %s (rule_score=%.2f; %s)", row["title"], classification.category, classification.rule_score, classification.rationale)
