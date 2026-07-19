"""
scrapedatshi.pipeline._pdf
~~~~~~~~~~~~~~~~~~~~~~~~~~~
PDF Extract methods:
    pdf_extract — extract text or tables from a PDF (URL or local file)

Billing:
    $0.0020 per file upload (local file)
    $0.0040 per URL fetch (server fetches the PDF)
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi.models import PdfExtractResult


class PdfMixin:
    """Mixin providing pdf_extract and pdf_extract_async methods."""

    _client: "ScrapedatshiClient"

    # ── PDF Extract ───────────────────────────────────────────────────────────

    def pdf_extract(
        self,
        *,
        url: str | None = None,
        file_path: str | Path | None = None,
        mode: str = "text",
        preserve_headings: bool = True,
    ) -> PdfExtractResult:
        """
        Extract clean text or structured tables from a PDF.

        Provide either ``url`` (a direct PDF URL) or ``file_path`` (a local PDF file).
        Exactly one must be supplied.

        Billing:
            - File upload: **$0.0020** per request
            - URL fetch:   **$0.0040** per request (server fetches the PDF)

        Args:
            url:               Direct URL to a PDF file (e.g. S3 link, CDN URL, ``https://.../report.pdf``).
            file_path:         Path to a local ``.pdf`` file.
            mode:              ``"text"`` (default) — returns clean Markdown text.
                               ``"tables"`` — returns structured table data as a list of dicts.
            preserve_headings: When ``mode="text"``, attempt to preserve heading structure
                               from the PDF (default: True).

        Returns:
            :class:`~scrapedatshi.models.PdfExtractResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.
            :class:`~scrapedatshi.exceptions.ValidationError`: Bad request (e.g. both url and file_path supplied).
            :class:`~scrapedatshi.exceptions.AuthError`: Invalid API key.
            ValueError: If neither or both of ``url`` / ``file_path`` are supplied.

        Example::

            # Extract text from a PDF URL
            result = client.pipeline.pdf_extract(url="https://example.com/report.pdf")
            print(result.text)
            print(f"Cost: ${result.credits_used:.4f}")

            # Extract text from a local PDF file
            result = client.pipeline.pdf_extract(file_path="./docs/manual.pdf")
            print(result.text)

            # Extract tables from a PDF URL
            result = client.pipeline.pdf_extract(
                url="https://example.com/data.pdf",
                mode="tables",
            )
            for table in result.tables or []:
                print(table)

            # Async version
            result = await client.pipeline.pdf_extract_async(
                url="https://example.com/report.pdf"
            )
        """
        if url is None and file_path is None:
            raise ValueError("pdf_extract() requires either url= or file_path=")
        if url is not None and file_path is not None:
            raise ValueError(
                "pdf_extract() accepts either url= or file_path=, not both"
            )

        form_data: dict = {"mode": mode}
        if not preserve_headings:
            form_data["preserve_headings"] = "false"

        if file_path is not None:
            path = Path(file_path)
            mime_type = mimetypes.guess_type(str(path))[0] or "application/pdf"
            with open(path, "rb") as f:
                files = {"pdf_file": (path.name, f, mime_type)}
                data = self._client._post(
                    "/portal/pdf/extract", files=files, data=form_data
                )
            source = path.name
        else:
            form_data["url"] = url  # type: ignore[assignment]
            data = self._client._post("/portal/pdf/extract", data=form_data)
            source = url  # type: ignore[assignment]

        return PdfExtractResult(
            source=data.get("source", source),
            mode=data.get("mode", mode),
            text=data.get("text"),
            tables=data.get("tables"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def pdf_extract_async(
        self,
        *,
        url: str | None = None,
        file_path: str | Path | None = None,
        mode: str = "text",
        preserve_headings: bool = True,
    ) -> PdfExtractResult:
        """Async version of :meth:`pdf_extract`."""
        if url is None and file_path is None:
            raise ValueError("pdf_extract_async() requires either url= or file_path=")
        if url is not None and file_path is not None:
            raise ValueError(
                "pdf_extract_async() accepts either url= or file_path=, not both"
            )

        form_data: dict = {"mode": mode}
        if not preserve_headings:
            form_data["preserve_headings"] = "false"

        if file_path is not None:
            path = Path(file_path)
            mime_type = mimetypes.guess_type(str(path))[0] or "application/pdf"
            with open(path, "rb") as f:
                files = {"pdf_file": (path.name, f, mime_type)}
                data = await self._client._post_async(
                    "/portal/pdf/extract", files=files, data=form_data
                )
            source = path.name
        else:
            form_data["url"] = url  # type: ignore[assignment]
            data = await self._client._post_async("/portal/pdf/extract", data=form_data)
            source = url  # type: ignore[assignment]

        return PdfExtractResult(
            source=data.get("source", source),
            mode=data.get("mode", mode),
            text=data.get("text"),
            tables=data.get("tables"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )
