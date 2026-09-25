import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Config
from app.downloader.document_downloader import DocumentDownloader, DownloadError


def make_config(root: Path) -> Config:
    return Config("https://www.mca.gov.in/", 100, 30, 1, 0, 2, 1, 5, 80, "tesseract", None, root / "data", root / "data/db.sqlite3", root / "data/logs/a.log", "test-agent")


class FakeResponse:
    url = "https://www.mca.gov.in/sample.pdf"
    status_code = 200
    headers = {"Content-Type": "application/pdf"}

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        yield self.payload

    def close(self):
        return None


class FakeSession:
    headers = {}

    def __init__(self, payload):
        self.payload = payload

    def get(self, *args, **kwargs):
        return FakeResponse(self.payload)


class DownloaderTests(unittest.TestCase):
    def test_rejects_non_pdf_response_and_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "doc.pdf"
            downloader = DocumentDownloader(make_config(Path(directory)), session=FakeSession(b"<html>403</html>"))
            with self.assertRaises(DownloadError):
                downloader.download("https://www.mca.gov.in/sample.pdf", dest)
            self.assertFalse(dest.exists())

    def test_accepts_pdf_and_hashes_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "doc.pdf"
            downloader = DocumentDownloader(make_config(Path(directory)), session=FakeSession(b"%PDF-1.4\nbody"))
            with patch.object(DocumentDownloader, "_validate_pdf", return_value=None):
                digest, size = downloader.download("https://www.mca.gov.in/sample.pdf", dest)
            self.assertEqual(size, len(b"%PDF-1.4\nbody"))
            self.assertEqual(len(digest), 64)
            self.assertTrue(dest.exists())

    def test_refuses_external_host(self):
        with tempfile.TemporaryDirectory() as directory:
            downloader = DocumentDownloader(make_config(Path(directory)), session=FakeSession(b""))
            with self.assertRaises(DownloadError):
                downloader.download("https://example.com/file.pdf", Path(directory) / "file.pdf")

    def test_does_not_follow_redirect_outside_mca(self):
        class RedirectSession:
            headers = {}

            def __init__(self):
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(url)
                response = FakeResponse(b"")
                response.status_code = 302
                response.headers = {"Location": "https://example.com/file.pdf"}
                return response

        with tempfile.TemporaryDirectory() as directory:
            session = RedirectSession()
            downloader = DocumentDownloader(make_config(Path(directory)), session=session)
            with self.assertRaises(DownloadError):
                downloader.download("https://www.mca.gov.in/redirect.pdf", Path(directory) / "file.pdf")
            self.assertEqual(session.calls, ["https://www.mca.gov.in/redirect.pdf"])
