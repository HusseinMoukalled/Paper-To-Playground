"""Acquire only the explicitly requested source; never follow local source links."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import url2pathname

import httpx

from playground.budget import RunBudget
from playground.failures import FailureCode
from playground.source.document import DocumentFormat
from playground.source.settings import SourceSettings
from playground.source.support import check_budget, fail


@dataclass(frozen=True, slots=True)
class AcquiredSource:
    source_id: str
    data: bytes
    format: DocumentFormat
    content_type: str | None = None


def detect_format(data: bytes, content_type: str | None = None) -> DocumentFormat:
    """Bytes are authoritative: suffixes/MIME alone cannot turn arbitrary files into papers."""
    prefix = data[:8192].lstrip(b"\xef\xbb\xbf \r\n\t").lower()
    if prefix.startswith(b"%pdf-"):
        return DocumentFormat.PDF
    if any(marker in prefix for marker in (b"<!doctype html", b"<html", b"<article", b"<body")):
        return DocumentFormat.HTML
    if content_type and "html" in content_type.lower() and b"<" in prefix and b">" in prefix:
        return DocumentFormat.HTML
    fail(FailureCode.PARSE_FAILED, "source_acquisition", "Source is not a supported PDF or static HTML document.")


def acquire_source(source_url: str, *, base_dir: Path | None = None,
                   allowed_root: Path | None = None, settings: SourceSettings | None = None,
                   budget: RunBudget | None = None, transport: httpx.BaseTransport | None = None) -> AcquiredSource:
    settings = settings or SourceSettings()
    check_budget(budget)
    parsed = urlsplit(source_url)
    remote = parsed.scheme.lower() in ("http", "https")
    content_type = None
    if remote:
        if not parsed.hostname or parsed.username or parsed.password:
            fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source URL must have a host and no credentials.")
        deadline = time.monotonic() + min(settings.timeout_seconds,
            budget.remaining_seconds - budget.finalization_reserve_seconds if budget else settings.timeout_seconds)
        data = None
        with httpx.Client(transport=transport, timeout=settings.timeout_seconds,
                          follow_redirects=True, max_redirects=settings.max_redirects,
                          trust_env=False) as client:
            for attempt in range(settings.transient_retries + 1):
                check_budget(budget)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source download deadline exceeded.")
                try:
                    with client.stream("GET", source_url, timeout=remaining,
                                       headers={"Accept": "application/pdf,text/html", "Accept-Encoding": "identity"}) as response:
                        if response.status_code in (429, 500, 502, 503, 504) and attempt < settings.transient_retries:
                            continue
                        response.raise_for_status()
                        content_type = response.headers.get("content-type")
                        length = response.headers.get("content-length")
                        if length and length.isdecimal() and int(length) > settings.max_bytes:
                            fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source exceeds the download size limit.")
                        chunks, size = [], 0
                        for chunk in response.iter_bytes(chunk_size=64 * 1024):
                            check_budget(budget)
                            if time.monotonic() > deadline:
                                fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source download deadline exceeded.")
                            size += len(chunk)
                            if size > settings.max_bytes:
                                fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source exceeds the download size limit.")
                            chunks.append(chunk)
                        data = b"".join(chunks)
                        break
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    if attempt == settings.transient_retries:
                        fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source download failed or timed out.")
                except httpx.HTTPError:
                    fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source HTTP request failed.")
        if data is None:
            fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source download failed.")
    else:
        # A Windows drive letter is a path, not a URI scheme.
        if parsed.scheme.lower() == "file":
            if parsed.netloc not in ("", "localhost"):
                fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Remote file shares are unsupported.")
            path = Path(url2pathname(parsed.path))
        elif parsed.scheme and not (len(parsed.scheme) == 1 and source_url[1:3] in (":\\", ":/")):
            fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Unsupported source URL scheme.")
        else:
            path = Path(source_url)
        if str(path).startswith(("\\\\", "//")):
            fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Remote file shares are unsupported.")
        path = ((base_dir or Path.cwd()) / path).resolve()
        if allowed_root is not None and not path.is_relative_to(allowed_root.resolve()):
            fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Source is outside the permitted source directory.")
        try:
            if not path.is_file():
                raise OSError("not a regular file")
            with path.open("rb") as stream:
                data = stream.read(settings.max_bytes + 1)
        except OSError:
            fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Requested local source is unavailable.")
        if len(data) > settings.max_bytes:
            fail(FailureCode.SOURCE_ACQUISITION_FAILED, "source_acquisition", "Local source exceeds the size limit.")
    check_budget(budget)
    return AcquiredSource("paper-" + hashlib.sha256(data).hexdigest(), data, detect_format(data, content_type), content_type)
