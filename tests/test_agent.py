import hashlib
import tempfile
import uuid
import unittest
from pathlib import Path

from app.agent.runner import AgentRunner
from app.config import Config
from app.database.repository import Repository
from app.models import Candidate


def make_config(root: Path, limit: int) -> Config:
    data = root / "data"
    return Config("https://www.mca.gov.in/", limit, 30, 1, 0, 4, 1, 5, 80, "tesseract", None, data, data / "metadata/db.sqlite3", data / "logs/agent.log", "test-agent")


class FakeDiscovery:
    def __init__(self, candidates):
        self.candidates = candidates

    def discover(self):
        return self.candidates


class FakeDownloader:
    def __init__(self, payload=b"%PDF-1.4\nbody"):
        self.payload = payload
        self.calls = 0

    def download(self, url, destination):
        self.calls += 1
        destination.write_bytes(self.payload)
        return hashlib.sha256(self.payload).hexdigest(), len(self.payload)


class FakeOCR:
    def extract_text(self, path):
        return "Companies Act, 2013 Notification G.S.R. 123(E)"


class AgentTests(unittest.TestCase):
    def test_stops_after_100_unique_and_never_attempts_document_101(self):
        class DistinctDownloader:
            def __init__(self):
                self.urls = []

            def download(self, url, destination):
                self.urls.append(url)
                payload = b"%PDF-1.4\n" + url.encode("ascii")
                destination.write_bytes(payload)
                return hashlib.sha256(payload).hexdigest(), len(payload)

        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 100)
            repo = Repository(config.database_path)
            candidates = [Candidate(f"https://www.mca.gov.in/doc{i}.pdf", f"Companies Act document {i}", "now") for i in range(101)]
            downloader = DistinctDownloader()
            runner = AgentRunner(config, repo, FakeDiscovery(candidates), downloader, FakeOCR())
            outcome = runner.run_once(owner="cap-100")
            self.assertEqual(outcome, "limit")
            self.assertEqual(len(downloader.urls), 100)
            self.assertEqual(repo.downloaded_count(), 100)
            doc101_id = str(uuid.uuid5(uuid.NAMESPACE_URL, candidates[100].source_url))
            self.assertIsNone(repo.get(doc101_id))
            reopened = Repository(config.database_path)
            second_downloader = DistinctDownloader()
            second_runner = AgentRunner(config, reopened, FakeDiscovery(candidates), second_downloader, FakeOCR())
            self.assertEqual(second_runner.run_once(owner="cap-after-restart"), "limit")
            self.assertEqual(reopened.downloaded_count(), 100)
            self.assertEqual(second_downloader.urls, [])

    def test_duplicate_content_does_not_increment_unique_count(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 100)
            repo = Repository(config.database_path)
            candidates = [Candidate(f"https://www.mca.gov.in/doc{i}.pdf", f"Companies Act document {i}", "now") for i in range(3)]
            runner = AgentRunner(config, repo, FakeDiscovery(candidates), FakeDownloader(), FakeOCR())
            runner.run_once(owner="duplicates")
            self.assertEqual(repo.downloaded_count(), 1)
            self.assertEqual(repo.status()["discovered"], 3)

    def test_mca_ui_candidate_without_companies_act_signal_is_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 100)
            repo = Repository(config.database_path)
            candidates = [
                Candidate("mca-ui://document/Notices/irrelevant", "Recruitment for MCA", "now"),
                Candidate("mca-ui://document/Circulars/relevant", "Companies Act circular", "now"),
            ]
            downloader = FakeDownloader()
            runner = AgentRunner(config, repo, FakeDiscovery(candidates), downloader, FakeOCR())
            runner.run_once(owner="relevance-filter")
            self.assertEqual(downloader.calls, 1)
            self.assertEqual(repo.downloaded_count(), 1)

    def test_stops_after_successful_unique_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 1)
            repo = Repository(config.database_path)
            candidates = [Candidate(f"https://www.mca.gov.in/doc{i}.pdf", f"Companies Act Notification {i}", "now") for i in range(3)]
            downloader = FakeDownloader()
            runner = AgentRunner(config, repo, FakeDiscovery(candidates), downloader, FakeOCR())
            runner.run_once(owner="test")
            self.assertEqual(repo.downloaded_count(), 1)
            self.assertEqual(downloader.calls, 1)

    def test_controlled_three_document_cycle(self):
        class DistinctDownloader:
            def download(self, url, destination):
                payload = b"%PDF-1.4\n" + url.encode("ascii")
                destination.write_bytes(payload)
                return hashlib.sha256(payload).hexdigest(), len(payload)

        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 3)
            repo = Repository(config.database_path)
            candidates = [Candidate(f"https://www.mca.gov.in/companies-act-{i}.pdf", f"Companies Act Notification {i}", "now") for i in range(3)]
            runner = AgentRunner(config, repo, FakeDiscovery(candidates), DistinctDownloader(), FakeOCR())
            runner.run_once(owner="controlled-three")
            self.assertEqual(repo.downloaded_count(), 3)
            self.assertEqual(repo.status()["classified"], 3)
            self.assertEqual(len(list((config.data_dir / "documents" / "Notifications").glob("*.pdf"))), 3)

    def test_failed_download_does_not_count(self):
        class FailedDownloader:
            def download(self, url, path):
                raise RuntimeError("temporary failure")

        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 3)
            repo = Repository(config.database_path)
            candidate = Candidate("https://www.mca.gov.in/companies-act-notice.pdf", "Companies Act Notification", "now")
            runner = AgentRunner(config, repo, FakeDiscovery([candidate]), FailedDownloader(), FakeOCR())
            runner.run_once(owner="test")
            self.assertEqual(repo.downloaded_count(), 0)
            self.assertEqual(repo.status()["errors"], 1)

    def test_resumes_downloaded_document_without_redownloading(self):
        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 3)
            repo = Repository(config.database_path)
            pdf = config.data_dir / "downloads" / "raw" / "resume.pdf"
            pdf.parent.mkdir(parents=True)
            pdf.write_bytes(b"%PDF-1.4\nbody")
            doc_id = "resume"
            repo.add_candidate(doc_id, "https://www.mca.gov.in/companies-act.pdf", "Companies Act")
            repo.update(doc_id, download_status="success", sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), local_path=str(pdf), file_size=pdf.stat().st_size)
            runner = AgentRunner(config, repo, FakeDiscovery([]), FakeDownloader(), FakeOCR())
            runner.run_once(owner="resume", process_existing_only=True)
            self.assertEqual(repo.get(doc_id)["processing_status"], "complete")
            self.assertEqual(repo.get(doc_id)["ocr_status"], "success")

    def test_ocr_failure_does_not_stop_processing_or_classification(self):
        class FailedOCR:
            def extract_text(self, path):
                raise RuntimeError("OCR engine unavailable")

        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 2)
            repo = Repository(config.database_path)
            candidate = Candidate("https://www.mca.gov.in/companies-act.pdf", "Companies Act, 2013", "now")
            runner = AgentRunner(config, repo, FakeDiscovery([candidate]), FakeDownloader(), FailedOCR())
            runner.run_once(owner="ocr-failure")
            doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, candidate.source_url))
            row = repo.get(doc_id)
            self.assertEqual(row["ocr_status"], "failed")
            self.assertEqual(row["classification_status"], "success")
            self.assertEqual(row["processing_status"], "error")
            retry = AgentRunner(config, repo, FakeDiscovery([]), FakeDownloader(), FakeOCR())
            retry.run_once(owner="ocr-retry", process_existing_only=True)
            row = repo.get(doc_id)
            self.assertEqual(row["ocr_status"], "success")
            self.assertEqual(row["processing_status"], "complete")

    def test_discovery_403_is_persisted_without_fabricating_document_downloads(self):
        class UnavailableDiscovery:
            def discover(self):
                raise RuntimeError("MCA document discovery unavailable: HTTP 403")

        with tempfile.TemporaryDirectory() as directory:
            config = make_config(Path(directory), 100)
            repo = Repository(config.database_path)
            runner = AgentRunner(config, repo, UnavailableDiscovery(), FakeDownloader(), FakeOCR())
            self.assertEqual(runner.run_once(owner="mca-403"), "unavailable")
            status = Repository(config.database_path).status()
            self.assertEqual(status["downloaded"], 0)
            self.assertEqual(status["discovery_errors"], 1)
