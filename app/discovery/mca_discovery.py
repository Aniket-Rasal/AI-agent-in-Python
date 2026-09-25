from __future__ import annotations

import logging
import time
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests

from app.config import Config
from app.models import Candidate

LOG = logging.getLogger(__name__)
RELEVANCE = ("companies act", "companiesact", "company law", "companies (", "companies rules")
HOME_PATH = "content/mca/global/en/home.html"
KNOWN_ACT_PDF = "https://www.mca.gov.in/content/dam/mca/pdf/CompaniesAct2013.pdf"


def is_relevant(value: str) -> bool:
    normalized = " ".join(value.casefold().replace("_", " ").replace("-", " ").split())
    return any(term in normalized for term in RELEVANCE)


def _normalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href is not None:
            self.links.append((self._href, " ".join(part for part in self._text if part)))
            self._href = None


class MCADiscovery:
    def __init__(self, config: Config, session: requests.Session | None = None, portal=None):
        self.config = config
        self.portal = portal
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent, "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8"})

    def _get_official(self, url: str) -> requests.Response:
        current = url
        for _ in range(6):
            response = self.session.get(current, timeout=self.config.timeout_seconds, allow_redirects=False)
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise requests.TooManyRedirects("MCA redirect omitted its Location header")
            target = urljoin(current, location)
            if not self._official(target):
                raise ValueError("MCA page redirects outside the official MCA host")
            current = target
        raise requests.TooManyRedirects("MCA redirect limit exceeded")

    def _official(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            return False
        configured = self.config.host
        host = parts.hostname.lower()
        return host == configured or ({host, configured} <= {"mca.gov.in", "www.mca.gov.in"})

    def discover(self) -> list[Candidate]:
        if self.portal is not None:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            candidates = [Candidate(KNOWN_ACT_PDF, "Companies Act, 2013", now)]
            candidates.extend(self.portal.discover())
            return candidates
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        root = urljoin(self.config.base_url, HOME_PATH)
        queue = deque([(root, 0)])
        visited: set[str] = set()
        candidates: dict[str, Candidate] = {}
        candidates[KNOWN_ACT_PDF] = Candidate(KNOWN_ACT_PDF, "Companies Act, 2013", now)

        while queue and len(visited) < self.config.max_pages:
            page_url, depth = queue.popleft()
            page_url = _normalize_url(page_url)
            if page_url in visited or not self._official(page_url):
                continue
            visited.add(page_url)
            try:
                response = self._get_official(page_url)
                response.raise_for_status()
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else "unknown"
                LOG.warning("MCA discovery stopped for %s (HTTP %s): %s", page_url, status, exc)
                if status == 403:
                    raise RuntimeError("MCA document discovery unavailable: HTTP 403") from exc
                continue
            except (requests.RequestException, ValueError) as exc:
                LOG.warning("MCA discovery request failed for %s: %s", page_url, exc)
                continue
            if not self._official(response.url):
                LOG.warning("Ignoring redirect outside the configured MCA host: %s", response.url)
                continue
            if "html" not in response.headers.get("Content-Type", "").lower():
                continue

            parser = _Links()
            parser.feed(response.text)
            for href, label in parser.links:
                target = _normalize_url(urljoin(response.url, href))
                if not self._official(target):
                    continue
                label = label or urlsplit(target).path.rsplit("/", 1)[-1]
                if urlsplit(target).path.lower().endswith(".pdf"):
                    if is_relevant(f"{label} {target}"):
                        candidates.setdefault(target, Candidate(target, label[:300], now))
                elif depth < self.config.max_depth and self._crawlable(target):
                    queue.append((target, depth + 1))
            if self.config.request_delay_seconds > 0:
                time.sleep(self.config.request_delay_seconds)

        LOG.info("MCA discovery visited %d page(s), found %d relevant PDF candidate(s)", len(visited), len(candidates))
        return list(candidates.values())

    @staticmethod
    def _crawlable(url: str) -> bool:
        path = urlsplit(url).path.lower()
        return path.endswith((".html", ".htm")) and not any(part in path for part in ("/login", "/registration", "/e-filing/"))
