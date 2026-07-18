"""
scrapedatshi.pipeline._chunk
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Scrape-to-Markdown and Chunk-to-JSON methods:
    scrape_url, scrape_file — return raw Markdown
    chunk_url, chunk_file, crawl — return structured JSON chunks

No embedding or vector DB required.
"""

from __future__ import annotations

import mimetypes
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi._file_parser import _extract_file_text_locally, _guess_source_type
from scrapedatshi.models import ChunkResult, CrawlChunkResult, ScrapeResult
from scrapedatshi.pipeline._crawl_helpers import _crawl_locally, _crawl_locally_async


class ChunkMixin:
    """Mixin providing scrape_url, scrape_file, chunk_url, chunk_file, and crawl methods."""

    _client: "ScrapedatshiClient"

    # ── Scrape to Markdown — URL ──────────────────────────────────────────────

    def scrape_url(
        self,
        url: str,
        *,
        selector: str | None = None,
        js_render: bool = False,
        cookies: dict | None = None,
        headers: dict | None = None,
        storage_state: dict | None = None,
    ) -> ScrapeResult:
        """
        Scrape a URL and return the full page content as clean Markdown.

        No chunking, no embedding, no vector DB required — this is the simplest
        way to get clean text from any URL.  In local-fetch mode (default), the
        page is fetched on your machine using your IP address.

        Args:
            url:           The URL to scrape.
            selector:      Optional CSS selector to target a specific element.
            js_render:     Use headless Chromium to render JavaScript before scraping.
            cookies:       Session cookies for authenticated scraping (local-fetch only).
            headers:       Additional HTTP headers (local-fetch only).
            storage_state: Playwright storage state dict for SSO/MFA authenticated scraping.

        Returns:
            :class:`~scrapedatshi.models.ScrapeResult` with ``markdown``, ``title``,
            ``source``, ``content_truncated``, ``credits_used``, ``credits_remaining``.
        """
        payload: dict = {"url": url}
        if selector:
            payload["selector"] = selector
        if js_render:
            payload["js_render"] = True

        if self._client.fetch_mode == "local":
            html = self._client._fetch_url_locally(
                url, cookies=cookies, extra_headers=headers
            )
            payload["html"] = html

        data = self._client._post("/v1/process-html", json=payload)
        metadata = data.get("metadata") or {}
        return ScrapeResult(
            markdown=data.get("markdown", ""),
            source=url,
            title=metadata.get("title") if isinstance(metadata, dict) else None,
            content_truncated=bool(data.get("content_truncated", False)),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def scrape_url_async(
        self,
        url: str,
        *,
        selector: str | None = None,
        js_render: bool = False,
        cookies: dict | None = None,
        headers: dict | None = None,
        storage_state: dict | None = None,
    ) -> ScrapeResult:
        """Async version of :meth:`scrape_url`."""
        payload: dict = {"url": url}
        if selector:
            payload["selector"] = selector
        if js_render:
            payload["js_render"] = True

        if self._client.fetch_mode == "local":
            html = await self._client._fetch_url_locally_async(
                url, cookies=cookies, extra_headers=headers
            )
            payload["html"] = html

        data = await self._client._post_async("/v1/process-html", json=payload)
        metadata = data.get("metadata") or {}
        return ScrapeResult(
            markdown=data.get("markdown", ""),
            source=url,
            title=metadata.get("title") if isinstance(metadata, dict) else None,
            content_truncated=bool(data.get("content_truncated", False)),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Scrape to Markdown — File ─────────────────────────────────────────────

    def scrape_file(
        self,
        file_path: str | Path,
    ) -> ScrapeResult:
        """
        Parse a local file and return its content as clean Markdown text.

        Supports PDF, MD, TXT, YAML, YML, JSON, CSV, XLSX, DOCX, IPYNB, HTML,
        XML, and all common code files (.py, .js, .ts, .sql, .go, .rb, etc.).
        In local-fetch mode (default), the file is parsed on your machine.

        Args:
            file_path: Path to the local file to parse.

        Returns:
            :class:`~scrapedatshi.models.ScrapeResult` with ``markdown``,
            ``source``, ``credits_used``, ``credits_remaining``.
        """
        path = Path(file_path)
        text = _extract_file_text_locally(path)
        payload: dict = {
            "url": f"file://{path.name}",
            "text": text,
            "source_type": _guess_source_type(path),
            # chunk_size=1 forces the server to return the full text as a single
            # "chunk" — we then extract the text and return it as raw Markdown.
            "chunk_size": 4096,
            "overlap": 0,
        }
        data = self._client._post("/v1/process-text", json=payload)
        # Reassemble all chunks back into a single Markdown string
        chunks = data.get("chunks", [])
        markdown = "\n\n".join(c.get("text", "") for c in chunks).strip()
        return ScrapeResult(
            markdown=markdown,
            source=path.name,
            title=None,
            content_truncated=False,
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def scrape_file_async(
        self,
        file_path: str | Path,
    ) -> ScrapeResult:
        """Async version of :meth:`scrape_file`."""
        import asyncio as _asyncio

        path = Path(file_path)
        text = await _asyncio.to_thread(_extract_file_text_locally, path)
        payload: dict = {
            "url": f"file://{path.name}",
            "text": text,
            "source_type": _guess_source_type(path),
            "chunk_size": 4096,
            "overlap": 0,
        }
        data = await self._client._post_async("/v1/process-text", json=payload)
        chunks = data.get("chunks", [])
        markdown = "\n\n".join(c.get("text", "") for c in chunks).strip()
        return ScrapeResult(
            markdown=markdown,
            source=path.name,
            title=None,
            content_truncated=False,
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Chunk to JSON — URL ───────────────────────────────────────────────────

    def chunk_url(
        self,
        url: str,
        *,
        selector: str | None = None,
        chunk_size: int = 512,
        overlap: int = 50,
        js_render: bool = False,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
        cookies: dict | None = None,
        headers: dict | None = None,
        allow_subdomains: bool = False,
    ) -> ChunkResult:
        """
        Scrape a URL, chunk the content, and return structured JSON chunks.
        No embedding or vector DB required.
        """
        payload: dict = {"url": url}
        if selector:
            payload["selector"] = selector
        if chunk_size != 512:
            payload["chunk_size"] = chunk_size
        if overlap != 50:
            payload["overlap"] = overlap
        if js_render:
            payload["js_render"] = True
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        if self._client.fetch_mode == "local":
            html = self._client._fetch_url_locally(
                url, cookies=cookies, extra_headers=headers
            )
            payload["html"] = html

        data = self._client._post("/v1/rag-chunk", json=payload)
        result = ChunkResult(
            chunks=data.get("chunks", []),
            total_chunks=data.get("chunk_count", len(data.get("chunks", []))),
            source=url,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            content_truncated=bool(data.get("content_truncated", False)),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )
        if result.contextual_retrieval_error:
            warnings.warn(
                f"scrapedatshi contextual retrieval warning: {result.contextual_retrieval_error}",
                stacklevel=2,
            )
        return result

    async def chunk_url_async(
        self,
        url: str,
        *,
        selector: str | None = None,
        chunk_size: int = 512,
        overlap: int = 50,
        js_render: bool = False,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
        cookies: dict | None = None,
        headers: dict | None = None,
        allow_subdomains: bool = False,
    ) -> ChunkResult:
        """Async version of :meth:`chunk_url`."""
        payload: dict = {"url": url}
        if selector:
            payload["selector"] = selector
        if chunk_size != 512:
            payload["chunk_size"] = chunk_size
        if overlap != 50:
            payload["overlap"] = overlap
        if js_render:
            payload["js_render"] = True
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        if self._client.fetch_mode == "local":
            html = await self._client._fetch_url_locally_async(
                url, cookies=cookies, extra_headers=headers
            )
            payload["html"] = html

        data = await self._client._post_async("/v1/rag-chunk", json=payload)
        return ChunkResult(
            chunks=data.get("chunks", []),
            total_chunks=data.get("chunk_count", len(data.get("chunks", []))),
            source=url,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            content_truncated=bool(data.get("content_truncated", False)),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Chunk to JSON — File ──────────────────────────────────────────────────

    def chunk_file(
        self,
        file_path: str | Path,
        *,
        chunk_size: int = 512,
        overlap: int = 50,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> ChunkResult:
        """
        Parse a local file and chunk its content into RAG-ready segments.
        Supports PDF, MD, TXT, YAML, YML, JSON, CSV, XLSX, DOCX, IPYNB, and code files.
        No embedding or vector DB required.
        """
        path = Path(file_path)

        if self._client.fetch_mode == "local":
            text = _extract_file_text_locally(path)
            payload: dict = {
                "url": f"file://{path.name}",
                "text": text,
                "source_type": _guess_source_type(path),
            }
            if chunk_size != 512:
                payload["chunk_size"] = chunk_size
            if overlap != 50:
                payload["overlap"] = overlap
            data = self._client._post("/v1/process-text", json=payload)
            all_chunks = data.get("chunks", [])
            return ChunkResult(
                chunks=all_chunks,
                total_chunks=data.get("chunk_count", len(all_chunks)),
                source=path.name,
                contextual_retrieval_used=False,
                contextual_retrieval_error=None,
                content_truncated=False,
                credits_used=float(data.get("credits_used", 0.0)),
                credits_remaining=float(data.get("credits_remaining", 0.0)),
            )

        # Server mode: upload file for server-side parsing
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        form_data: dict = {}
        if chunk_size != 512:
            form_data["chunk_size"] = str(chunk_size)
        if overlap != 50:
            form_data["overlap"] = str(overlap)
        if contextual_retrieval:
            form_data["contextual_retrieval"] = "true"
            if llm_provider:
                form_data["llm_provider"] = llm_provider
            if llm_api_key:
                form_data["llm_api_key"] = llm_api_key
            if llm_model:
                form_data["llm_model"] = llm_model

        with open(path, "rb") as f:
            files = {"files": (path.name, f, mime_type)}
            data = self._client._post("/v1/ingest-chunk", files=files, data=form_data)

        results = data.get("results", [])
        all_chunks = []
        for r in results:
            all_chunks.extend(r.get("chunks", []))

        return ChunkResult(
            chunks=all_chunks,
            total_chunks=data.get("total_chunks", len(all_chunks)),
            source=path.name,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            content_truncated=False,
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def chunk_file_async(
        self,
        file_path: str | Path,
        *,
        chunk_size: int = 512,
        overlap: int = 50,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> ChunkResult:
        """Async version of :meth:`chunk_file`."""
        path = Path(file_path)

        if self._client.fetch_mode == "local":
            import asyncio as _asyncio

            text = await _asyncio.to_thread(_extract_file_text_locally, path)
            payload: dict = {
                "url": f"file://{path.name}",
                "text": text,
                "source_type": _guess_source_type(path),
            }
            if chunk_size != 512:
                payload["chunk_size"] = chunk_size
            if overlap != 50:
                payload["overlap"] = overlap
            data = await self._client._post_async("/v1/process-text", json=payload)
            all_chunks = data.get("chunks", [])
            return ChunkResult(
                chunks=all_chunks,
                total_chunks=data.get("chunk_count", len(all_chunks)),
                source=path.name,
                contextual_retrieval_used=False,
                contextual_retrieval_error=None,
                content_truncated=False,
                credits_used=float(data.get("credits_used", 0.0)),
                credits_remaining=float(data.get("credits_remaining", 0.0)),
            )

        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        form_data: dict = {}
        if chunk_size != 512:
            form_data["chunk_size"] = str(chunk_size)
        if overlap != 50:
            form_data["overlap"] = str(overlap)
        if contextual_retrieval:
            form_data["contextual_retrieval"] = "true"
            if llm_provider:
                form_data["llm_provider"] = llm_provider
            if llm_api_key:
                form_data["llm_api_key"] = llm_api_key
            if llm_model:
                form_data["llm_model"] = llm_model

        with open(path, "rb") as f:
            files = {"files": (path.name, f, mime_type)}
            data = await self._client._post_async(
                "/v1/ingest-chunk", files=files, data=form_data
            )

        results = data.get("results", [])
        all_chunks = []
        for r in results:
            all_chunks.extend(r.get("chunks", []))

        return ChunkResult(
            chunks=all_chunks,
            total_chunks=data.get("total_chunks", len(all_chunks)),
            source=path.name,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            content_truncated=False,
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Chunk to JSON — Crawl ─────────────────────────────────────────────────

    def crawl(
        self,
        url: str,
        *,
        max_pages: int | None = None,
        crawl_mode: str = "sitemap",
        selector: str | None = None,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        js_render: bool = False,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
        cookies: dict | None = None,
        headers: dict | None = None,
        allow_subdomains: bool = False,
    ) -> CrawlChunkResult:
        """
        Crawl a website, chunk all pages, and return structured JSON.
        No embedding or vector DB required.
        """
        use_local = self._client.fetch_mode == "local"

        if use_local:
            return _crawl_locally(
                client=self._client,
                url=url,
                crawl_mode=crawl_mode,
                max_pages=max_pages if max_pages is not None else 50,
                selector=selector,
                include_pattern=include_pattern,
                exclude_pattern=exclude_pattern,
                js_render=js_render,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
                cookies=cookies,
                headers=headers,
                allow_subdomains=allow_subdomains,
            )

        payload: dict = {"url": url, "crawl_mode": crawl_mode}
        if max_pages is not None:
            payload["max_pages"] = max_pages
        if selector:
            payload["selector"] = selector
        if include_pattern:
            payload["include_pattern"] = include_pattern
        if exclude_pattern:
            payload["exclude_pattern"] = exclude_pattern
        if js_render:
            payload["js_render"] = True
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        data = self._client._post("/v1/crawl-chunk", json=payload)
        chunks_by_page = data.get("chunks_by_page", [])
        all_chunks = []
        for page in chunks_by_page:
            all_chunks.extend(page.get("chunks", []))

        return CrawlChunkResult(
            chunks=all_chunks,
            total_chunks=data.get("total_chunks", len(all_chunks)),
            pages_crawled=data.get("pages_crawled", 0),
            source_url=url,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def crawl_async(
        self,
        url: str,
        *,
        max_pages: int | None = None,
        crawl_mode: str = "sitemap",
        selector: str | None = None,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        js_render: bool = False,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
        cookies: dict | None = None,
        headers: dict | None = None,
        allow_subdomains: bool = False,
    ) -> CrawlChunkResult:
        """Async version of :meth:`crawl`."""
        use_local = self._client.fetch_mode == "local"

        if use_local:
            return await _crawl_locally_async(
                client=self._client,
                url=url,
                crawl_mode=crawl_mode,
                max_pages=max_pages if max_pages is not None else 50,
                selector=selector,
                include_pattern=include_pattern,
                exclude_pattern=exclude_pattern,
                js_render=js_render,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
                cookies=cookies,
                headers=headers,
                allow_subdomains=allow_subdomains,
            )

        payload: dict = {"url": url, "crawl_mode": crawl_mode}
        if max_pages is not None:
            payload["max_pages"] = max_pages
        if selector:
            payload["selector"] = selector
        if include_pattern:
            payload["include_pattern"] = include_pattern
        if exclude_pattern:
            payload["exclude_pattern"] = exclude_pattern
        if js_render:
            payload["js_render"] = True
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        data = await self._client._post_async("/v1/crawl-chunk", json=payload)
        chunks_by_page = data.get("chunks_by_page", [])
        all_chunks = []
        for page in chunks_by_page:
            all_chunks.extend(page.get("chunks", []))

        return CrawlChunkResult(
            chunks=all_chunks,
            total_chunks=data.get("total_chunks", len(all_chunks)),
            pages_crawled=data.get("pages_crawled", 0),
            source_url=url,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )
