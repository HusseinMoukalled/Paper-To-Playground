import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from playground.failures import FailureCode, PlaygroundError
from playground.source.acquire import acquire_source, detect_format
from playground.source.document import DocumentFormat
from playground.source.settings import SourceSettings
from tests.fixtures.source_factory import HTML_PAPER, paper_pdf


class AcquisitionTests(unittest.TestCase):
    def test_local_pdf_and_file_uri_and_stable_source_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.data"
            path.write_bytes(paper_pdf())
            first = acquire_source(path.name, base_dir=path.parent)
            second = acquire_source(path.as_uri())
            self.assertEqual(first.source_id, second.source_id)
            self.assertEqual(first.format, DocumentFormat.PDF)

    def test_missing_unsupported_and_outside_root(self):
        for path in ("missing.pdf", "ftp://host/paper", "file://remote/paper.pdf"):
            with self.subTest(path=path), self.assertRaises(PlaygroundError):
                acquire_source(path)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(PlaygroundError):
                acquire_source("../secret.pdf", base_dir=root, allowed_root=root)

    def test_magic_bytes_override_extension_and_mime(self):
        self.assertEqual(detect_format(HTML_PAPER, "application/pdf"), DocumentFormat.HTML)
        with self.assertRaises(PlaygroundError):
            detect_format(b"plain secret file", "application/pdf")

    def test_remote_success_and_one_transient_retry(self):
        requests = []
        def handler(request):
            requests.append(request)
            return httpx.Response(503 if len(requests) == 1 else 200, content=HTML_PAPER,
                                  headers={"content-type": "text/html"})
        source = acquire_source("https://paper.invalid/paper", transport=httpx.MockTransport(handler))
        self.assertEqual(source.format, DocumentFormat.HTML)
        self.assertEqual(len(requests), 2)

    def test_network_timeout_is_sanitized_and_bounded(self):
        attempts = []
        def handler(request):
            attempts.append(1)
            raise httpx.ReadTimeout("secret-key-in-exception", request=request)
        with self.assertRaises(PlaygroundError) as caught:
            acquire_source("https://paper.invalid", transport=httpx.MockTransport(handler))
        self.assertEqual(len(attempts), 2)
        self.assertNotIn("secret-key", str(caught.exception))

    def test_nontransient_http_error_has_no_retry(self):
        attempts = []
        def handler(request):
            attempts.append(1)
            return httpx.Response(404)
        with self.assertRaises(PlaygroundError):
            acquire_source("https://paper.invalid", transport=httpx.MockTransport(handler))
        self.assertEqual(len(attempts), 1)

    def test_redirects_are_bounded(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "/again"}))
        with self.assertRaises(PlaygroundError):
            acquire_source("https://paper.invalid", transport=transport)

    def test_size_limits_local_and_remote(self):
        settings = SourceSettings(max_bytes=10)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "paper.pdf"
            path.write_bytes(paper_pdf())
            with self.assertRaises(PlaygroundError):
                acquire_source(str(path), settings=settings)
        for headers in ({}, {"content-length": "100"}):
            transport = httpx.MockTransport(lambda request: httpx.Response(200, content=HTML_PAPER, headers=headers))
            with self.subTest(headers=headers), self.assertRaises(PlaygroundError):
                acquire_source("https://paper.invalid", transport=transport, settings=settings)

    def test_total_deadline(self):
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=HTML_PAPER))
        with patch("playground.source.acquire.time.monotonic", side_effect=[0, 0, 31]), self.assertRaises(PlaygroundError):
            acquire_source("https://paper.invalid", transport=transport, settings=SourceSettings(transient_retries=0))
