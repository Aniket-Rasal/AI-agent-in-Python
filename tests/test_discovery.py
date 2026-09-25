import tempfile
import unittest
from pathlib import Path

import requests

from app.config import Config
from app.discovery.mca_discovery import KNOWN_ACT_PDF, MCADiscovery


def make_config(root: Path) -> Config:
    return Config("https://www.mca.gov.in/", 100, 30, 1, 0, 4, 1, 5, 80, "tesseract", None, root / "data", root / "db.sqlite3", root / "agent.log", "test-agent")


class FakeResponse:
    def __init__(self, url, body, status=200):
        self.url = url
        self.text = body
        self.status_code = status
        self.headers = {"Content-Type": "text/html"}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def close(self):
        return None


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.headers = {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class DiscoveryTests(unittest.TestCase):
    def test_follows_official_homepage_links_and_filters_irrelevant_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = "https://www.mca.gov.in/content/mca/global/en/home.html"
            body = """
                <a href='/content/dam/mca/pdf/companies-act-amendment.pdf'>Companies Act Amendment Rules</a>
                <a href='https://example.com/companies-act.pdf'>Companies Act</a>
                <a href='/content/dam/mca/pdf/general.pdf'>Annual report</a>
            """
            session = FakeSession(FakeResponse(root, body))
            results = MCADiscovery(make_config(Path(directory)), session=session).discover()
            urls = {item.source_url for item in results}
            self.assertIn(KNOWN_ACT_PDF, urls)
            self.assertIn("https://www.mca.gov.in/content/dam/mca/pdf/companies-act-amendment.pdf", urls)
            self.assertEqual(len(urls), 2)
            self.assertTrue(all(call[1]["allow_redirects"] is False for call in session.calls))

    def test_reports_discovery_unavailable_on_forbidden_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = "https://www.mca.gov.in/content/mca/global/en/home.html"
            session = FakeSession(FakeResponse(root, "", status=403))
            with self.assertRaisesRegex(RuntimeError, "MCA document discovery unavailable: HTTP 403"):
                MCADiscovery(make_config(Path(directory)), session=session).discover()
            self.assertEqual(len(session.calls), 1)
