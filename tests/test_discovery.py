import tempfile
import unittest
from dataclasses import replace
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

    def test_follows_linked_html_pagination_and_deduplicates_pdf_candidates(self):
        root = "https://www.mca.gov.in/content/mca/global/en/home.html"
        page1 = "https://www.mca.gov.in/content/mca/global/en/notices/page1.html"
        page2 = "https://www.mca.gov.in/content/mca/global/en/notices/page2.html"
        first_pdf = "https://www.mca.gov.in/content/dam/mca/pdf/companies-act-circular.pdf"
        second_pdf = "https://www.mca.gov.in/content/dam/mca/pdf/companies-act-notification.pdf"

        class PaginatedSession:
            def __init__(self):
                self.headers = {}
                self.calls = []

            def get(self, url, **kwargs):
                self.calls.append(url)
                if url == root:
                    body = f'<a href="{page1}">Circulars page 1</a>'
                elif url == page1:
                    body = f'<a href="{page2}">Next page</a><a href="{first_pdf}">Companies Act Circular</a>'
                else:
                    body = f'<a href="{first_pdf}">Companies Act Circular</a><a href="{second_pdf}">Companies Act Notification</a>'
                return FakeResponse(url, body)

        with tempfile.TemporaryDirectory() as directory:
            session = PaginatedSession()
            config = replace(make_config(Path(directory)), max_depth=2)
            candidates = MCADiscovery(config, session=session).discover()
            urls = [item.source_url for item in candidates]

            self.assertIn(first_pdf, urls)
            self.assertIn(second_pdf, urls)
            self.assertEqual(urls.count(first_pdf), 1)
            self.assertEqual(session.calls, [root, page1, page2])

    def test_reports_discovery_unavailable_on_forbidden_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = "https://www.mca.gov.in/content/mca/global/en/home.html"
            session = FakeSession(FakeResponse(root, "", status=403))
            with self.assertRaisesRegex(RuntimeError, "MCA document discovery unavailable: HTTP 403"):
                MCADiscovery(make_config(Path(directory)), session=session).discover()
            self.assertEqual(len(session.calls), 1)
