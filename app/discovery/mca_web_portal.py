from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

from app.config import Config
from app.models import Candidate

LOG = logging.getLogger(__name__)
HOME_PATH = "content/mca/global/en/home.html"
SECTIONS = (
    "Important Updates",
    "What's New",
    "Notices",
    "Circulars",
    "Recent Reports",
    "Quotations & Tenders",
    "Press Release",
    "Vacancies",
)


class MCAWebError(RuntimeError):
    pass


@dataclass(frozen=True)
class _WebDocument:
    section: str
    title: str
    date: str


class MCAWebPortal:
    """Use MCA's visible public pages and document links through a regular browser."""

    def __init__(self, config: Config):
        self.config = config
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._documents: dict[str, _WebDocument] = {}

    def _ensure_page(self) -> None:
        if self._page is not None:
            return
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise MCAWebError("Browser collection needs Playwright. Install requirements and run 'python -m playwright install chromium'.") from exc

        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(headless=True)
            self._context = self._browser.new_context(accept_downloads=True)
            self._page = self._context.new_page()
            response = self._page.goto(
                self.config.base_url.rstrip("/") + "/" + HOME_PATH,
                wait_until="domcontentloaded",
                timeout=self.config.timeout_seconds * 1000,
            )
            if response is None or response.status >= 400:
                status = response.status if response is not None else "no response"
                raise MCAWebError(f"MCA homepage returned {status}")
            if self._page.get_by_role("heading", name="Notifications & Updates").count() == 0:
                raise MCAWebError("MCA public page did not show Notifications & Updates; stopping without bypassing the page response")
        except PlaywrightTimeoutError as exc:
            self.close()
            raise MCAWebError(f"Timed out loading MCA's public homepage: {exc}") from exc
        except Exception:
            self.close()
            raise

    @staticmethod
    def _source_key(section: str, title: str, date: str) -> str:
        digest = hashlib.sha256(f"{section}\0{title}\0{date}".encode("utf-8")).hexdigest()
        return f"mca-ui://document/{quote(section, safe='')}/{digest}"

    def discover(self) -> list[Candidate]:
        self._ensure_page()
        assert self._page is not None
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        self._documents.clear()
        found: dict[str, Candidate] = {}

        for section in SECTIONS:
            button = self._page.get_by_role("button", name=section, exact=True)
            if button.count() == 0:
                continue
            button.click()
            links = self._page.locator("a.doc-link:visible")
            try:
                links.first.wait_for(timeout=min(self.config.timeout_seconds, 5) * 1000)
            except PlaywrightTimeoutError:
                continue
            records = self._page.locator("a.doc-link:visible").evaluate_all(
                "els => els.map(a => ({title: a.querySelector('.titleSearchTabs')?.getAttribute('data-title') || '', "
                "date: a.querySelector('.doc-date')?.getAttribute('data-title') || '', "
                "pdf: a.parentElement?.querySelector('img')?.getAttribute('alt') === 'pdf-icon'}))"
            )
            for record in records:
                title = " ".join(record["title"].split())
                if not title or not record["pdf"]:
                    continue
                date = " ".join((record.get("date") or "").split())
                source_url = self._source_key(section, title, date)
                self._documents[source_url] = _WebDocument(section, title, date)
                discovered = datetime.now(timezone.utc).isoformat(timespec="seconds")
                found.setdefault(source_url, Candidate(source_url, title[:300], discovered))
            if self.config.request_delay_seconds > 0:
                import time

                time.sleep(self.config.request_delay_seconds)

        LOG.info("MCA public UI listed %d PDF candidate(s) across %d section(s)", len(found), len(SECTIONS))
        return list(found.values())

    def fetch(self, source_url: str) -> bytes:
        self._ensure_page()
        assert self._page is not None and self._context is not None
        parts = urlsplit(source_url)
        if parts.scheme == "mca-ui":
            key = source_url
            document = self._documents.get(key)
            if document is None:
                raise MCAWebError("MCA UI candidate expired; run discovery again before downloading")
            button = self._page.get_by_role("button", name=document.section, exact=True)
            button.click()
            title_locator = self._page.locator("p.titleSearchTabs").filter(has_text=document.title).first
            title_locator.wait_for(timeout=self.config.timeout_seconds * 1000)
            card = title_locator.locator("xpath=ancestor::a[contains(@class,'doc-link')]")
            responses = []

            def capture(response) -> None:
                if response.request.is_navigation_request():
                    responses.append(response)

            self._context.on("response", capture)
            popup = None
            try:
                with self._page.expect_popup(timeout=self.config.timeout_seconds * 1000) as popup_info:
                    card.click()
                popup = popup_info.value
                popup.wait_for_load_state("domcontentloaded", timeout=self.config.timeout_seconds * 1000)
                response = next((item for item in reversed(responses) if item.url == popup.url), None)
                if response is None:
                    raise MCAWebError("MCA document link opened without a readable response")
                if response.status >= 400:
                    raise MCAWebError(f"MCA document link returned HTTP {response.status}")
                content_type = response.headers.get("content-type", "").lower()
                if "pdf" not in content_type:
                    raise MCAWebError(f"MCA document link returned {content_type or 'an unknown content type'}, not a PDF")
                return response.body()
            finally:
                self._context.remove_listener("response", capture)
                if popup is not None:
                    popup.close()

        if parts.scheme != "https" or parts.hostname not in {"www.mca.gov.in", "mca.gov.in"}:
            raise MCAWebError("Refusing a source outside the official MCA HTTPS site")
        download_page = self._context.new_page()
        try:
            response = download_page.goto(source_url, wait_until="domcontentloaded", timeout=self.config.timeout_seconds * 1000)
            if response is None or response.status >= 400:
                status = response.status if response is not None else "no response"
                raise MCAWebError(f"MCA document returned {status}")
            if "pdf" not in response.headers.get("content-type", "").lower():
                raise MCAWebError("MCA document link did not return a PDF")
            return response.body()
        finally:
            download_page.close()

    def close(self) -> None:
        self._page = None
        self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
