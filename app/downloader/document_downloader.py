from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.config import Config
from app.utils import sha256_file

LOG = logging.getLogger(__name__)


class DownloadError(RuntimeError):
    pass


class DocumentDownloader:
    def __init__(self, config: Config, session: requests.Session | None = None, portal=None):
        self.config = config
        self.portal = portal
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": config.user_agent})
        if session is None:
            retry = Retry(total=3, connect=3, read=2, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504), allowed_methods=frozenset({"GET"}), respect_retry_after_header=True)
            self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def _official(self, url: str) -> bool:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        return parts.scheme == "https" and (host == self.config.host or {host, self.config.host} <= {"mca.gov.in", "www.mca.gov.in"})

    def download(self, url: str, destination: Path) -> tuple[str, int]:
        if self.portal is not None:
            try:
                payload = self.portal.fetch(url)
            except Exception as exc:
                raise DownloadError(str(exc)) from exc
            return self._store_payload(payload, destination)
        if not self._official(url):
            raise DownloadError("Refusing non-HTTPS or non-MCA URL")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            response = self._get_official(url)
            with response:
                response.raise_for_status()
                if not self._official(response.url):
                    raise DownloadError("MCA URL redirected outside the configured official host")
                with tempfile.NamedTemporaryFile(prefix="mca-", suffix=".part", dir=destination.parent, delete=False) as temp:
                    temp_name = temp.name
                    first = b""
                    size = 0
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        if len(first) < 5:
                            first += chunk[: 5 - len(first)]
                        temp.write(chunk)
                        size += len(chunk)
                    temp.flush()
                    os.fsync(temp.fileno())
            if size < 8 or first != b"%PDF-":
                raise DownloadError("Response is empty or does not have a PDF signature")
            self._validate_pdf(Path(temp_name))
            digest = sha256_file(Path(temp_name))
            os.replace(temp_name, destination)
            temp_name = None
            return digest, size
        except (requests.RequestException, OSError) as exc:
            raise DownloadError(str(exc)) from exc
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    def _store_payload(self, payload: bytes, destination: Path) -> tuple[str, int]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        if len(payload) < 8 or payload[:5] != b"%PDF-":
            raise DownloadError("Response is empty or does not have a PDF signature")
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="mca-browser-", suffix=".part", dir=destination.parent, delete=False) as temp:
                temp_name = temp.name
                temp.write(payload)
                temp.flush()
                os.fsync(temp.fileno())
            staged = Path(temp_name)
            self._validate_pdf(staged)
            digest = sha256_file(staged)
            os.replace(staged, destination)
            temp_name = None
            return digest, len(payload)
        except OSError as exc:
            raise DownloadError(str(exc)) from exc
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    def import_local_pdf(self, source: Path, destination: Path) -> tuple[str, int]:
        """Validate and stage a PDF supplied by the user, without making a network request."""
        source = Path(source).expanduser()
        if not source.is_file():
            raise DownloadError(f"Local PDF does not exist or is not a file: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with source.open("rb") as input_file, tempfile.NamedTemporaryFile(
                prefix="mca-import-", suffix=".part", dir=destination.parent, delete=False
            ) as temp:
                temp_name = temp.name
                first = input_file.read(5)
                if first != b"%PDF-":
                    raise DownloadError("Local file does not have a PDF signature")
                temp.write(first)
                shutil.copyfileobj(input_file, temp, length=64 * 1024)
                temp.flush()
                os.fsync(temp.fileno())
                size = temp.tell()
            if size < 8:
                raise DownloadError("Local PDF is empty or too small to be valid")
            staged = Path(temp_name)
            self._validate_pdf(staged)
            digest = sha256_file(staged)
            os.replace(staged, destination)
            temp_name = None
            return digest, size
        except OSError as exc:
            raise DownloadError(str(exc)) from exc
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _validate_pdf(path: Path) -> None:
        try:
            import pymupdf as fitz

            with fitz.open(path) as document:
                if document.page_count < 1:
                    raise DownloadError("PDF contains no pages")
        except ImportError:
            return
        except DownloadError:
            raise
        except Exception as exc:
            raise DownloadError(f"PDF parser rejected the response: {exc}") from exc

    def _get_official(self, url: str) -> requests.Response:
        current = url
        for _ in range(6):
            response = self.session.get(current, stream=True, timeout=self.config.timeout_seconds, allow_redirects=False)
            if response.status_code not in (301, 302, 303, 307, 308):
                return response
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise DownloadError("MCA redirect omitted its Location header")
            target = urljoin(current, location)
            if not self._official(target):
                raise DownloadError("MCA redirect points outside the configured official host")
            current = target
        raise DownloadError("MCA redirect limit exceeded")
