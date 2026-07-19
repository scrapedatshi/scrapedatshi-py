"""
scrapedatshi.pipeline
~~~~~~~~~~~~~~~~~~~~~
PipelineNamespace — all pipeline methods, both sync and async.

Accessed via client.pipeline.*

Sync methods use httpx.Client (blocking).
Async methods use httpx.AsyncClient (non-blocking, for asyncio).

Billing:
    Credits are deducted after each successful API call. Failed requests are not charged.
    Every response includes ``credits_used`` and ``credits_remaining`` fields.
    See services/credits.py on the server for current pricing constants.

    If your balance is too low, :class:`~scrapedatshi.exceptions.InsufficientCreditsError`
    is raised (HTTP 402). Top up at https://scrapedatshi.com/portal/billing.
"""

from __future__ import annotations

import mimetypes
import os
import re
import time
import warnings
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi._domain_utils import _is_matching_domain_scope
from scrapedatshi._file_parser import _extract_file_text_locally, _guess_source_type
from scrapedatshi.models import (
    AutoRagResult,
    ChunkResult,
    CrawlChunkResult,
    ExtractCrawlPageResult,
    ExtractCrawlResult,
    ExtractResult,
    IngestFolderResult,
    IngestResult,
    InspectVectorDBResult,
    QueryResult,
    QueryVectorDBResult,
    RagChatResult,
    SuggestedModel,
    SyncResult,
)


class PipelineNamespace:
    """
    All pipeline operations, accessible via ``client.pipeline``.

    Chunk-to-JSON (no embedding required — available to all accounts):
        - chunk_url()        / chunk_url_async()
        - chunk_file()       / chunk_file_async()
        - crawl()            / crawl_async()

    Full Pipeline (embed + vector DB inject):
        - sync()             / sync_async()
        - ingest()           / ingest_async()
        - autorag()          / autorag_async()

    Schema Extraction (extract structured data from any URL using your LLM):
        - extract()          / extract_async()
        - extract_crawl()    / extract_crawl_async()

    All methods return typed response models with ``credits_used`` and
    ``credits_remaining`` fields for programmatic spend tracking.

    Supported providers:
        See :mod:`scrapedatshi.providers` for a full reference of supported
        embedding providers, vector databases, and LLM providers.
    """

    def __init__(self, client: "ScrapedatshiClient") -> None:
        self._client = client

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
    ) -> ChunkResult:
        """
        Scrape a URL, chunk the content, and return structured JSON chunks.
        No embedding or vector DB required.

        Args:
            url: The web URL to scrape and chunk.
            selector: Optional CSS selector to target a specific element
                (e.g. ``"article"``, ``".content"``).
            chunk_size: Target token count per chunk (default: 512, range: 64–4096).
            overlap: Token overlap between consecutive chunks (default: 50).
            js_render: If True, uses a headless Chromium browser (Playwright) to
                fully render JavaScript before scraping. Required for SPAs and
                JS-heavy pages. Adds a surcharge per fetch.
            contextual_retrieval: Enable RAG 2.0 contextual enrichment. For each chunk,
                an LLM generates a unique context string describing the document identity,
                section identity, and specific entities in that chunk. This context is
                prepended to the chunk text before embedding, boosting retrieval accuracy
                by 35–50%. Billed at **$0.0010 per chunk** that is successfully enriched.
            llm_provider: LLM provider for contextual retrieval (e.g. ``"openai"``).
                See :data:`scrapedatshi.providers.LLM_PROVIDERS` for supported providers.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name (e.g. ``"gpt-4o-mini"``).

        Returns:
            :class:`~scrapedatshi.models.ChunkResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.
            :class:`~scrapedatshi.exceptions.ValidationError`: Bad request payload.
            :class:`~scrapedatshi.exceptions.AuthError`: Invalid API key.

        Example::

            result = client.pipeline.chunk_url("https://docs.example.com")
            for chunk in result.chunks:
                print(chunk.content)
            print(f"Cost: ${result.credits_used:.4f}")

            # With contextual retrieval — each chunk gets unique LLM-generated context
            result = client.pipeline.chunk_url(
                "https://docs.example.com",
                contextual_retrieval=True,
                llm_provider="openai",
                llm_api_key="sk-...",
                llm_model="gpt-4o-mini",
            )
            for chunk in result.chunks:
                print(chunk.context)        # per-chunk LLM context
                print(chunk.original_text)  # raw text before enrichment
                print(chunk.content)        # combined for embedding
            if result.contextual_retrieval_error:
                print(f"CR warning: {result.contextual_retrieval_error}")

            # With JS rendering for JavaScript-heavy pages
            result = client.pipeline.chunk_url(
                "https://spa.example.com",
                js_render=True,
            )
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

        # Local-fetch mode (default): fetch URL on the caller's machine, submit HTML
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

        # Local-fetch mode (default): fetch URL on the caller's machine, submit HTML
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
        Supports PDF, MD, TXT, YAML, YML, and JSON files.
        No embedding or vector DB required.

        In local-fetch mode (default), the file is parsed on your machine using
        your own CPU — no heavy PDF processing on our server.  The extracted text
        is submitted to /v1/process-text for chunking only.

        In server-fetch mode (fetch_mode="server"), the file is uploaded to our
        server for parsing and chunking (legacy behaviour).

        Args:
            file_path: Path to the local file to parse and chunk.
            chunk_size: Target token count per chunk (default: 512).
            overlap: Token overlap between consecutive chunks (default: 50).
            contextual_retrieval: Enable RAG 2.0 contextual enrichment.
            llm_provider: LLM provider for contextual retrieval.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name.

        Returns:
            :class:`~scrapedatshi.models.ChunkResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.

        Example::

            result = client.pipeline.chunk_file("./docs/manual.pdf")
            print(f"Got {result.total_chunks} chunks from {result.source}")
            print(f"Cost: ${result.credits_used:.4f}")
        """
        path = Path(file_path)

        if self._client.fetch_mode == "local":
            # Local mode: parse the file on this machine, send text to server
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

        # Server mode: upload file for server-side parsing (legacy)
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

        # /v1/ingest-chunk returns per-file results array
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
            # Local mode: parse the file on this machine, send text to server
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

        # Server mode: upload file for server-side parsing (legacy)
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

    # ── Chunk to JSON — Sitemap Crawl ─────────────────────────────────────────

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

        Two crawl modes are available:
            - ``"sitemap"`` (default): Reads the site's ``sitemap.xml`` to discover URLs.
              Works best for documentation sites and blogs.
            - ``"spider"``: Follows ``<a href>`` links from the root URL.
              Works on any website — no sitemap required. More compute-intensive.

        In local-fetch mode (default), the crawl runs on the caller's machine.
        Each page is fetched using the caller's IP address and submitted to the
        server for chunking. Cookies and headers are only sent to URLs within
        the permitted domain scope — preventing credential leakage to external
        domains.

        In server-fetch mode (``fetch_mode="server"``), the server performs the
        crawl. ``cookies`` and ``headers`` are not forwarded to the server.

        Args:
            url: The root domain or sitemap URL to crawl.
            max_pages: Maximum number of pages to crawl (default: 50 for local mode).
                Sitemap mode: up to 200 pages (server hard cap).
                Spider mode: up to 200 pages (BFS link-following — more compute-intensive).
                Defaults to the server's recommended value if not specified.
            crawl_mode: ``"sitemap"`` (default) or ``"spider"``.
            selector: Optional CSS selector applied to every page.
            include_pattern: Only crawl URLs containing this substring (e.g. ``"/docs/"``).
            exclude_pattern: Skip URLs containing this substring (e.g. ``"/blog/"``).
            js_render: If True, uses a headless browser to render JS before scraping.
                Adds a surcharge per page fetched. In local-fetch mode, this
                automatically falls back to server-fetch mode (JS rendering requires
                Playwright on the server).
            contextual_retrieval: Enable RAG 2.0 contextual enrichment.
                Adds a surcharge per URL crawled.
            llm_provider: LLM provider for contextual retrieval.
                See :data:`scrapedatshi.providers.LLM_PROVIDERS` for supported providers.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name.
            cookies: Optional dict of cookies to include with every page request
                (e.g. ``{"session": "abc123"}``). Only sent to URLs within the
                permitted domain scope — never leaked to external domains.
                Only used in local-fetch mode.
            headers: Optional dict of additional request headers (e.g.
                ``{"Authorization": "Bearer eyJ..."}``). Same domain-isolation
                rules apply as ``cookies``. Only used in local-fetch mode.
            allow_subdomains: If True, also crawl subdomains of the root domain
                (e.g. ``wiki.company.com`` when root is ``company.com``).
                Cookies and headers are shared across all subdomains within scope.
                Multi-part TLDs (.co.uk, .com.br) are handled safely.
                Default: False (exact domain match only).

        Returns:
            :class:`~scrapedatshi.models.CrawlChunkResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.

        Example::

            result = client.pipeline.crawl("https://example.com", max_pages=10)
            print(f"Crawled {result.pages_crawled} pages → {result.total_chunks} chunks")
            print(f"Cost: ${result.credits_used:.4f}")

            # Spider mode — works on any site, no sitemap needed
            result = client.pipeline.crawl(
                "https://example.com",
                crawl_mode="spider",
                max_pages=5,
                include_pattern="/docs/",
            )

            # Authenticated crawl — cookies stay on your machine
            result = client.pipeline.crawl(
                "https://internal.company.com",
                cookies={"session": "abc123"},
                headers={"Authorization": "Bearer eyJ..."},
                max_pages=20,
            )

            # Subdomain scope — also crawls wiki.company.com, docs.company.com
            result = client.pipeline.crawl(
                "https://company.com",
                cookies={"session": "abc123"},
                allow_subdomains=True,
                max_pages=30,
            )
        """
        # js_render in local mode requires server-side Playwright — fall back to server fetch
        use_local = self._client.fetch_mode == "local" and not js_render
        if self._client.fetch_mode == "local" and js_render:
            warnings.warn(
                "crawl(): js_render=True requires server-side Playwright. "
                "Falling back to server-fetch mode for this crawl. "
                "Cookies and headers will NOT be forwarded to the server.",
                stacklevel=2,
            )

        if use_local:
            return _crawl_locally(
                client=self._client,
                url=url,
                crawl_mode=crawl_mode,
                max_pages=max_pages if max_pages is not None else 50,
                selector=selector,
                include_pattern=include_pattern,
                exclude_pattern=exclude_pattern,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
                cookies=cookies,
                headers=headers,
                allow_subdomains=allow_subdomains,
            )

        # Server-fetch mode (or js_render fallback): delegate to /v1/crawl-chunk
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

        # /v1/crawl-chunk returns chunks_by_page — flatten to a single list
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
        # js_render in local mode requires server-side Playwright — fall back to server fetch
        use_local = self._client.fetch_mode == "local" and not js_render
        if self._client.fetch_mode == "local" and js_render:
            warnings.warn(
                "crawl_async(): js_render=True requires server-side Playwright. "
                "Falling back to server-fetch mode for this crawl. "
                "Cookies and headers will NOT be forwarded to the server.",
                stacklevel=2,
            )

        if use_local:
            return await _crawl_locally_async(
                client=self._client,
                url=url,
                crawl_mode=crawl_mode,
                max_pages=max_pages if max_pages is not None else 50,
                selector=selector,
                include_pattern=include_pattern,
                exclude_pattern=exclude_pattern,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
                cookies=cookies,
                headers=headers,
                allow_subdomains=allow_subdomains,
            )

        # Server-fetch mode (or js_render fallback): delegate to /v1/crawl-chunk
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

    # ── Full Pipeline — URL Sync ──────────────────────────────────────────────

    def sync(
        self,
        url: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_config: dict,
        embedding_model: str | None = None,
        embedding_endpoint: str | None = None,
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
    ) -> SyncResult:
        """
        Full pipeline: scrape a URL, embed chunks, and inject into a vector DB.

        Args:
            url: The web URL to scrape, embed, and inject.
            embedding_provider: Embedding provider key (e.g. ``"openai"``).
                See :data:`scrapedatshi.providers.EMBEDDING_PROVIDERS` for all options.
            embedding_api_key: API key for the embedding provider.
                Pass an empty string ``""`` for Ollama (no key required).
            vector_db: Vector DB provider key (e.g. ``"pinecone"``).
                See :data:`scrapedatshi.providers.VECTOR_DB_PROVIDERS` for all options.
            vector_db_config: Provider-specific configuration dict. Required fields
                vary by provider — see :data:`scrapedatshi.providers.VECTOR_DB_PROVIDERS`.

                Pinecone example::

                    vector_db_config={"api_key": "pc-...", "index_host": "https://my-index.svc.pinecone.io"}

                Qdrant example::

                    vector_db_config={"url": "https://your-cluster.qdrant.io", "collection_name": "docs"}

                Supabase example::

                    vector_db_config={"connection_string": "postgresql://...", "table_name": "documents"}

            embedding_model: Model name for the embedding provider. Required for all
                providers. Check your provider's documentation for available models.
            embedding_endpoint: Public endpoint URL for local embedding providers
                (Ollama only). Must be a publicly accessible HTTPS URL — use ngrok
                to expose your local Ollama instance: ``ngrok http 11434``.
            selector: Optional CSS selector to target a specific element.
            chunk_size: Target token count per chunk (default: 512).
            overlap: Token overlap between consecutive chunks (default: 50).
            js_render: If True, uses a headless browser to render JS before scraping.
                Adds a surcharge per fetch.
            contextual_retrieval: Enable RAG 2.0 contextual enrichment.
            llm_provider: LLM provider for contextual retrieval.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name for the LLM provider. Required when
                ``contextual_retrieval=True``. Check your provider's documentation
                for available models.
            cookies: Optional dict of cookies to include with the page request
                (e.g. ``{"session": "abc123"}``). Only used in local-fetch mode.
            headers: Optional dict of additional request headers (e.g.
                ``{"Authorization": "Bearer eyJ..."}``). Only used in local-fetch mode.

        Returns:
            :class:`~scrapedatshi.models.SyncResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.

        Example::

            result = client.pipeline.sync(
                url="https://docs.example.com",
                embedding_provider="openai",
                embedding_api_key="sk-...",
                vector_db="pinecone",
                vector_db_config={
                    "api_key": "pc-...",
                    "index_host": "https://my-index-abc123.svc.pinecone.io",
                },
            )
            print(f"Upserted {result.vectors_upserted} vectors")
            print(f"Cost: ${result.credits_used:.4f}")

            # Authenticated sync — fetch the page with your session cookie
            result = client.pipeline.sync(
                url="https://internal.company.com/wiki/api-docs",
                cookies={"session": "abc123"},
                embedding_provider="openai",
                embedding_api_key="sk-...",
                vector_db="pinecone",
                vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
            )
        """
        embedding: dict = {"provider": embedding_provider, "api_key": embedding_api_key}
        if embedding_model:
            embedding["model"] = embedding_model
        if embedding_endpoint:
            embedding["endpoint"] = embedding_endpoint

        vdb: dict = {"provider": vector_db, **vector_db_config}

        payload: dict = {"url": url, "embedding": embedding, "vector_db": vdb}
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

        # Local-fetch mode (default): fetch URL on the caller's machine, submit HTML
        if self._client.fetch_mode == "local":
            html = self._client._fetch_url_locally(
                url, cookies=cookies, extra_headers=headers
            )
            payload["html"] = html

        data = self._client._post("/v1/sync", json=payload)
        return SyncResult(
            status=data.get("status", "success"),
            chunks_created=data.get("chunks_created", 0),
            vectors_upserted=data.get("vectors_upserted", 0),
            total_tokens=data.get(
                "total_tokens_estimated", data.get("total_tokens", 0)
            ),
            embedding_provider=embedding_provider,
            vector_db_provider=vector_db,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def sync_async(
        self,
        url: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_config: dict,
        embedding_model: str | None = None,
        embedding_endpoint: str | None = None,
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
    ) -> SyncResult:
        """Async version of :meth:`sync`."""
        embedding: dict = {"provider": embedding_provider, "api_key": embedding_api_key}
        if embedding_model:
            embedding["model"] = embedding_model
        if embedding_endpoint:
            embedding["endpoint"] = embedding_endpoint

        vdb: dict = {"provider": vector_db, **vector_db_config}

        payload: dict = {"url": url, "embedding": embedding, "vector_db": vdb}
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

        # Local-fetch mode (default): fetch URL on the caller's machine, submit HTML
        if self._client.fetch_mode == "local":
            html = await self._client._fetch_url_locally_async(
                url, cookies=cookies, extra_headers=headers
            )
            payload["html"] = html

        data = await self._client._post_async("/v1/sync", json=payload)
        return SyncResult(
            status=data.get("status", "success"),
            chunks_created=data.get("chunks_created", 0),
            vectors_upserted=data.get("vectors_upserted", 0),
            total_tokens=data.get(
                "total_tokens_estimated", data.get("total_tokens", 0)
            ),
            embedding_provider=embedding_provider,
            vector_db_provider=vector_db,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Full Pipeline — Folder Ingest ────────────────────────────────────────

    def ingest_folder(
        self,
        folder_path: str | Path,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_config: dict,
        embedding_model: str | None = None,
        embedding_endpoint: str | None = None,
        chunk_size: int = 512,
        overlap: int = 50,
        file_extensions: list[str] | None = None,
        recursive: bool = True,
        max_files: int | None = None,
        batch_delay: float = 0.5,
        json_text_keys: list[str] | None = None,
    ) -> IngestFolderResult:
        """
        Bulk ingest an entire folder of files — chunk, embed, and inject into a vector DB.

        Designed for users who have pre-scraped content from external tools (Scrapy,
        Playwright, wget, etc.) and want to embed and inject it into their vector DB.

        Supports ``.md``, ``.txt``, ``.json``, ``.yaml``, and ``.yml`` files.
        For JSON files, automatically detects Scrapy/crawler array exports and
        extracts text from each item individually.

        All processing runs on your machine — no server-side crawling. Rate limit
        errors from your embedding provider are handled automatically with
        exponential backoff.

        Args:
            folder_path: Path to the folder containing files to ingest.
            embedding_provider: Embedding provider key (e.g. ``"openai"``).
            embedding_api_key: API key for the embedding provider.
            vector_db: Vector DB provider key (e.g. ``"pinecone"``).
            vector_db_config: Provider-specific configuration dict.
            embedding_model: Model name for the embedding provider.
            embedding_endpoint: Public endpoint URL for Ollama (ngrok URL).
            chunk_size: Target token count per chunk (default: 512).
            overlap: Token overlap between consecutive chunks (default: 50).
            file_extensions: File extensions to process. Default: ``[".md", ".txt", ".json", ".yaml", ".yml"]``.
            recursive: If True, recurse into subdirectories (default: True).
            max_files: Maximum number of files to process. Default: unlimited.
            batch_delay: Seconds to wait between files (default: 0.5). Increase
                to avoid hitting embedding provider rate limits.
            json_text_keys: Keys to look for when extracting text from JSON items.
                Default: ``["text", "content", "html", "body", "markdown", "description"]``.
                Used for Scrapy/crawler JSON array exports.

        Returns:
            :class:`~scrapedatshi.models.IngestFolderResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.

        Example::

            # Ingest a Scrapy output folder
            result = client.pipeline.ingest_folder(
                folder_path="./scrapy_output/",
                embedding_provider="openai",
                embedding_api_key="sk-...",
                embedding_model="text-embedding-3-small",
                vector_db="pinecone",
                vector_db_config={
                    "api_key": "pc-...",
                    "index_host": "https://my-index-abc123.svc.pinecone.io",
                },
            )
            print(f"Processed {result.files_processed} files → {result.vectors_upserted} vectors")
            print(f"Cost: ${result.credits_used:.4f}")
            for err in result.errors:
                print(f"  Failed: {err['file']} — {err['error']}")

            # Ingest a single large Scrapy JSON dump (array of items)
            result = client.pipeline.ingest_folder(
                folder_path="./",
                file_extensions=[".json"],
                embedding_provider="openai",
                embedding_api_key="sk-...",
                embedding_model="text-embedding-3-small",
                vector_db="qdrant",
                vector_db_config={"url": "https://...", "collection_name": "docs"},
                batch_delay=1.0,  # slower = safer for large batches
            )
        """
        path = Path(folder_path)
        if not path.is_dir():
            raise ValueError(f"folder_path must be a directory: {folder_path}")

        exts = tuple(file_extensions or list(_INGEST_FOLDER_EXTENSIONS))
        keys = tuple(json_text_keys or list(_JSON_TEXT_KEYS))

        return _ingest_folder_locally(
            client=self._client,
            folder_path=path,
            embedding_provider=embedding_provider,
            embedding_api_key=embedding_api_key,
            vector_db=vector_db,
            vector_db_config=vector_db_config,
            embedding_model=embedding_model,
            embedding_endpoint=embedding_endpoint,
            chunk_size=chunk_size,
            overlap=overlap,
            file_extensions=exts,
            recursive=recursive,
            max_files=max_files,
            batch_delay=batch_delay,
            json_text_keys=keys,
        )

    async def ingest_folder_async(
        self,
        folder_path: str | Path,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_config: dict,
        embedding_model: str | None = None,
        embedding_endpoint: str | None = None,
        chunk_size: int = 512,
        overlap: int = 50,
        file_extensions: list[str] | None = None,
        recursive: bool = True,
        max_files: int | None = None,
        batch_delay: float = 0.5,
        json_text_keys: list[str] | None = None,
    ) -> IngestFolderResult:
        """Async version of :meth:`ingest_folder`."""
        path = Path(folder_path)
        if not path.is_dir():
            raise ValueError(f"folder_path must be a directory: {folder_path}")

        exts = tuple(file_extensions or list(_INGEST_FOLDER_EXTENSIONS))
        keys = tuple(json_text_keys or list(_JSON_TEXT_KEYS))

        return await _ingest_folder_locally_async(
            client=self._client,
            folder_path=path,
            embedding_provider=embedding_provider,
            embedding_api_key=embedding_api_key,
            vector_db=vector_db,
            vector_db_config=vector_db_config,
            embedding_model=embedding_model,
            embedding_endpoint=embedding_endpoint,
            chunk_size=chunk_size,
            overlap=overlap,
            file_extensions=exts,
            recursive=recursive,
            max_files=max_files,
            batch_delay=batch_delay,
            json_text_keys=keys,
        )

    # ── Full Pipeline — File Ingest ───────────────────────────────────────────

    def ingest(
        self,
        file_path: str | Path,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_config: dict,
        embedding_model: str | None = None,
        embedding_endpoint: str | None = None,
        chunk_size: int = 512,
        overlap: int = 50,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> IngestResult:
        """
        Full pipeline: upload a local file, embed chunks, and inject into a vector DB.

        Args:
            file_path: Path to the local file to upload, embed, and inject.
                Supported formats: .pdf, .md, .txt, .yaml, .yml, .json
            embedding_provider: Embedding provider key (e.g. ``"openai"``).
                See :data:`scrapedatshi.providers.EMBEDDING_PROVIDERS` for all options.
            embedding_api_key: API key for the embedding provider.
                Pass an empty string ``""`` for Ollama (no key required).
            vector_db: Vector DB provider key (e.g. ``"pinecone"``).
                See :data:`scrapedatshi.providers.VECTOR_DB_PROVIDERS` for all options.
            vector_db_config: Provider-specific configuration dict.
                See :meth:`sync` for examples.
            embedding_model: Model name for the embedding provider. Required for all
                providers. Check your provider's documentation for available models.
            embedding_endpoint: Public endpoint URL for local embedding providers
                (Ollama only). Must be a publicly accessible HTTPS URL — use ngrok
                to expose your local Ollama instance: ``ngrok http 11434``.
            chunk_size: Target token count per chunk (default: 512).
            overlap: Token overlap between consecutive chunks (default: 50).
            contextual_retrieval: Enable RAG 2.0 contextual enrichment.
            llm_provider: LLM provider for contextual retrieval.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name for the LLM provider. Required when
                ``contextual_retrieval=True``. Check your provider's documentation
                for available models.

        Returns:
            :class:`~scrapedatshi.models.IngestResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.

        Example::

            result = client.pipeline.ingest(
                file_path="./docs/manual.pdf",
                embedding_provider="openai",
                embedding_api_key="sk-...",
                vector_db="qdrant",
                vector_db_config={
                    "url": "https://your-cluster.qdrant.io",
                    "collection_name": "documents",
                    "api_key": "qdrant-key",
                },
            )
            print(f"Ingested {result.chunks_created} chunks → {result.vectors_upserted} vectors")
        """
        path = Path(file_path)
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        embedding_cfg = {"provider": embedding_provider, "api_key": embedding_api_key}
        if embedding_model:
            embedding_cfg["model"] = embedding_model
        if embedding_endpoint:
            embedding_cfg["endpoint"] = embedding_endpoint

        vdb_cfg = {"provider": vector_db, **vector_db_config}

        import json as _json

        form_data: dict = {
            "embedding_config": _json.dumps(embedding_cfg),
            "vector_db_config": _json.dumps(vdb_cfg),
        }
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
            data = self._client._post("/v1/ingest", files=files, data=form_data)

        return IngestResult(
            status="success" if data.get("files_failed", 0) == 0 else "partial",
            chunks_created=data.get("total_chunks_created", 0),
            vectors_upserted=data.get("total_vectors_upserted", 0),
            total_tokens=data.get("total_tokens_estimated", 0),
            embedding_provider=embedding_provider,
            vector_db_provider=vector_db,
            filename=path.name,
            contextual_retrieval_used=bool(contextual_retrieval),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def ingest_async(
        self,
        file_path: str | Path,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_config: dict,
        embedding_model: str | None = None,
        embedding_endpoint: str | None = None,
        chunk_size: int = 512,
        overlap: int = 50,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> IngestResult:
        """Async version of :meth:`ingest`."""
        path = Path(file_path)
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        embedding_cfg = {"provider": embedding_provider, "api_key": embedding_api_key}
        if embedding_model:
            embedding_cfg["model"] = embedding_model
        if embedding_endpoint:
            embedding_cfg["endpoint"] = embedding_endpoint

        vdb_cfg = {"provider": vector_db, **vector_db_config}

        import json as _json

        form_data: dict = {
            "embedding_config": _json.dumps(embedding_cfg),
            "vector_db_config": _json.dumps(vdb_cfg),
        }
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
                "/v1/ingest", files=files, data=form_data
            )

        return IngestResult(
            status="success" if data.get("files_failed", 0) == 0 else "partial",
            chunks_created=data.get("total_chunks_created", 0),
            vectors_upserted=data.get("total_vectors_upserted", 0),
            total_tokens=data.get("total_tokens_estimated", 0),
            embedding_provider=embedding_provider,
            vector_db_provider=vector_db,
            filename=path.name,
            contextual_retrieval_used=bool(contextual_retrieval),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Schema Extraction ─────────────────────────────────────────────────────

    def extract(
        self,
        url: str,
        *,
        schema: dict[str, str],
        llm_provider: str,
        llm_api_key: str,
        llm_model: str | None = None,
        selector: str | None = None,
        extract_as_list: bool = False,
        js_render: bool = False,
        click_selector: str | None = None,
    ) -> ExtractResult:
        """
        Scrape a URL and extract structured data matching your schema using an LLM.

        You bring your own LLM key — scrapedatshi handles the scraping and
        orchestration. Supports OpenAI, Anthropic, and Google Gemini.

        Args:
            url: The web URL to scrape and extract from.
            schema: Dict mapping field names to description strings. The LLM uses
                these descriptions to understand what to extract.

                Example::

                    schema={
                        "title": "string — the product name",
                        "price": "number — the price in USD",
                        "in_stock": "boolean — whether the item is in stock",
                        "description": "string — the product description",
                    }

            llm_provider: LLM provider to use (``"openai"``, ``"anthropic"``, or ``"gemini"``).
                See :data:`scrapedatshi.providers.LLM_PROVIDERS` for details.
            llm_api_key: Your LLM provider API key.
            llm_model: Optional model override. Defaults vary by provider:
                - openai: ``"gpt-4o-mini"``
                - anthropic: ``"claude-3-haiku-20240307"``
                - gemini: ``"gemini-1.5-flash"``
            selector: Optional CSS selector to target a specific section of the page
                before extraction (e.g. ``"article"``, ``".product-details"``).
            extract_as_list: If True, extracts ALL matching items on the page as a
                JSON array instead of a single object. Use for pages with multiple
                items (product listings, article feeds, search results, etc.).
            js_render: If True, uses a headless Chromium browser (Playwright) to
                fully render JavaScript before extracting. Required for SPAs and
                JS-heavy pages. Adds a surcharge per fetch.
            click_selector: Optional CSS selector for an element to click after page
                load. Use for interaction-gated content (tabs, accordions, load-more
                buttons). Only used when ``js_render=True``.

        Returns:
            :class:`~scrapedatshi.models.ExtractResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.
            :class:`~scrapedatshi.exceptions.ValidationError`: Bad schema or request.
            :class:`~scrapedatshi.exceptions.AuthError`: Invalid API key.

        Example — extract a single product::

            result = client.pipeline.extract(
                url="https://example.com/products/widget-pro",
                schema={
                    "title": "string — the product name",
                    "price": "number — the price in USD",
                    "in_stock": "boolean — whether the item is in stock",
                },
                llm_provider="openai",
                llm_api_key="sk-...",
            )
            print(result.extracted)
            # → {"title": "Widget Pro", "price": 29.99, "in_stock": True}
            print(f"Cost: ${result.credits_used:.4f}")

        Example — extract all products from a listing page::

            result = client.pipeline.extract(
                url="https://example.com/products",
                schema={
                    "title": "string — the product name",
                    "price": "number — the price in USD",
                },
                llm_provider="openai",
                llm_api_key="sk-...",
                extract_as_list=True,
            )
            print(f"Extracted {result.item_count} products")
            for product in result.extracted:
                print(f"  {product['title']}: ${product['price']}")
        """
        payload: dict = {
            "url": url,
            "schema": schema,
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
        }
        if llm_model:
            payload["llm_model"] = llm_model
        if selector:
            payload["selector"] = selector
        if extract_as_list:
            payload["extract_as_list"] = True
        if js_render:
            payload["js_render"] = True
        if click_selector:
            payload["click_selector"] = click_selector

        data = self._client._post("/v1/extract", json=payload)

        extracted = data.get("extracted", {})
        item_count = data.get("item_count")
        if item_count is None and isinstance(extracted, list):
            item_count = len(extracted)

        return ExtractResult(
            extracted=extracted,
            field_count=data.get("field_count", len(schema)),
            item_count=item_count,
            url=url,
            llm_provider=llm_provider,
            llm_model=data.get(
                "llm_model", llm_model or f"(default for {llm_provider})"
            ),
            schema_fields=data.get("schema_fields", list(schema.keys())),
            js_render=js_render,
            content_warning=data.get("content_warning"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def extract_async(
        self,
        url: str,
        *,
        schema: dict[str, str],
        llm_provider: str,
        llm_api_key: str,
        llm_model: str | None = None,
        selector: str | None = None,
        extract_as_list: bool = False,
        js_render: bool = False,
        click_selector: str | None = None,
    ) -> ExtractResult:
        """Async version of :meth:`extract`."""
        payload: dict = {
            "url": url,
            "schema": schema,
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
        }
        if llm_model:
            payload["llm_model"] = llm_model
        if selector:
            payload["selector"] = selector
        if extract_as_list:
            payload["extract_as_list"] = True
        if js_render:
            payload["js_render"] = True
        if click_selector:
            payload["click_selector"] = click_selector

        data = await self._client._post_async("/v1/extract", json=payload)

        extracted = data.get("extracted", {})
        item_count = data.get("item_count")
        if item_count is None and isinstance(extracted, list):
            item_count = len(extracted)

        return ExtractResult(
            extracted=extracted,
            field_count=data.get("field_count", len(schema)),
            item_count=item_count,
            url=url,
            llm_provider=llm_provider,
            llm_model=data.get(
                "llm_model", llm_model or f"(default for {llm_provider})"
            ),
            schema_fields=data.get("schema_fields", list(schema.keys())),
            js_render=js_render,
            content_warning=data.get("content_warning"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Schema Extraction via Crawl ───────────────────────────────────────────

    def extract_crawl(
        self,
        url: str,
        *,
        schema: dict[str, str],
        llm_provider: str,
        llm_api_key: str,
        llm_model: str | None = None,
        crawl_mode: str = "sitemap",
        max_pages: int = 5,
        selector: str | None = None,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        extract_as_list: bool = False,
    ) -> ExtractCrawlResult:
        """
        Crawl a domain and extract structured data from every page using your LLM.

        Combines site crawling with schema extraction in a single call. Each page
        is processed independently — failed pages return an error object without
        aborting the batch. Only successfully extracted pages are billed.

        Two crawl modes are available:
            - ``"sitemap"`` (default): Reads the site's ``sitemap.xml`` to discover URLs.
            - ``"spider"``: Follows ``<a href>`` links from the root URL.

        Args:
            url: The root domain to crawl (e.g. ``"https://example.com"``).
            schema: Dict mapping field names to description strings.

                Example::

                    schema={
                        "title": "string — the product name",
                        "price": "number — the price in USD",
                        "in_stock": "boolean — whether the item is in stock",
                    }

            llm_provider: LLM provider to use (``"openai"``, ``"anthropic"``, or ``"gemini"``).
                See :data:`scrapedatshi.providers.LLM_PROVIDERS` for details.
            llm_api_key: Your LLM provider API key.
            llm_model: Optional model override. Standard models (mini, flash, haiku) use
                an 8,000 char context window. Advanced models use 30,000 chars.
            crawl_mode: ``"sitemap"`` (default) or ``"spider"``.
            max_pages: Maximum pages to crawl and extract from.
                Sitemap mode: up to 100 pages. Spider mode: up to 25 pages.
            selector: Optional CSS selector applied to every page before extraction.
            include_pattern: Only crawl URLs containing this substring (e.g. ``"/products/"``).
            exclude_pattern: Skip URLs containing this substring (e.g. ``"/blog/"``).
            extract_as_list: If True, extracts ALL matching items on each page as a
                JSON array instead of a single object per page.

        Returns:
            :class:`~scrapedatshi.models.ExtractCrawlResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.
            :class:`~scrapedatshi.exceptions.ServerBusyError`: Server at capacity — retry after ``e.retry_after`` seconds.
            :class:`~scrapedatshi.exceptions.ValidationError`: Bad schema or request.
            :class:`~scrapedatshi.exceptions.AuthError`: Invalid API key.

        Billing:
            Per successfully extracted page only:
            ``$0.0020 + $0.0030 + (N_fields × $0.0001)`` per page.

            Example: 10 pages × 5 fields = 10 × $0.0055 = **$0.055**

        Example — extract products from an entire catalogue::

            result = client.pipeline.extract_crawl(
                url="https://example.com/products",
                schema={
                    "title": "string — the product name",
                    "price": "number — the price in USD",
                    "in_stock": "boolean — whether the item is in stock",
                },
                llm_provider="openai",
                llm_api_key="sk-...",
                max_pages=20,
                include_pattern="/products/",
            )

            print(f"Extracted {result.pages_extracted}/{result.pages_attempted} pages")
            print(f"Cost: ${result.credits_used:.4f}")

            for page in result.results:
                if page.ok:
                    print(f"  {page.url}: {page.extracted}")
                else:
                    print(f"  {page.url}: FAILED — {page.error}")

            # Access only successful results
            for page in result.successful_results:
                print(page.extracted["title"], page.extracted["price"])

        Example — spider crawl with retry on server busy::

            import time
            from scrapedatshi.exceptions import ServerBusyError

            try:
                result = client.pipeline.extract_crawl(
                    url="https://example.com",
                    schema={"title": "string — the page title"},
                    llm_provider="openai",
                    llm_api_key="sk-...",
                    crawl_mode="spider",
                    max_pages=10,
                )
            except ServerBusyError as e:
                wait = e.retry_after or 30
                print(f"Server busy — retrying in {wait}s")
                time.sleep(wait)
                # retry...
        """
        payload: dict = {
            "url": url,
            "schema": schema,
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
            "crawl_mode": crawl_mode,
            "max_pages": max_pages,
        }
        if llm_model:
            payload["llm_model"] = llm_model
        if selector:
            payload["selector"] = selector
        if include_pattern:
            payload["include_pattern"] = include_pattern
        if exclude_pattern:
            payload["exclude_pattern"] = exclude_pattern
        if extract_as_list:
            payload["extract_as_list"] = True

        data = self._client._post("/v1/extract-crawl", json=payload)
        return _parse_extract_crawl_result(data)

    async def extract_crawl_async(
        self,
        url: str,
        *,
        schema: dict[str, str],
        llm_provider: str,
        llm_api_key: str,
        llm_model: str | None = None,
        crawl_mode: str = "sitemap",
        max_pages: int = 5,
        selector: str | None = None,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        extract_as_list: bool = False,
    ) -> ExtractCrawlResult:
        """Async version of :meth:`extract_crawl`."""
        payload: dict = {
            "url": url,
            "schema": schema,
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
            "crawl_mode": crawl_mode,
            "max_pages": max_pages,
        }
        if llm_model:
            payload["llm_model"] = llm_model
        if selector:
            payload["selector"] = selector
        if include_pattern:
            payload["include_pattern"] = include_pattern
        if exclude_pattern:
            payload["exclude_pattern"] = exclude_pattern
        if extract_as_list:
            payload["extract_as_list"] = True

        data = await self._client._post_async("/v1/extract-crawl", json=payload)
        return _parse_extract_crawl_result(data)

    # ── AutoRAG — Full Crawl Pipeline ────────────────────────────────────────

    def autorag(
        self,
        url: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_config: dict,
        embedding_model: str | None = None,
        crawl_mode: str = "sitemap",
        max_pages: int = 5,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        selector: str | None = None,
        chunk_size: int = 512,
        overlap: int = 50,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> AutoRagResult:
        """
        Full AutoRAG pipeline: crawl a domain, chunk every page, embed, and inject
        into a vector DB in a single call.

        Args:
            url: The root domain to crawl (e.g. ``"https://docs.example.com"``).
            embedding_provider: Embedding provider key (e.g. ``"openai"``).
                See :data:`scrapedatshi.providers.EMBEDDING_PROVIDERS` for all options.
            embedding_api_key: API key for the embedding provider.
                Pass an empty string ``""`` for Ollama (no key required).
            vector_db: Vector DB provider key (e.g. ``"pinecone"``).
                See :data:`scrapedatshi.providers.VECTOR_DB_PROVIDERS` for all options.
            vector_db_config: Provider-specific configuration dict.
                See :meth:`sync` for examples.
            embedding_model: Model name for the embedding provider.
            crawl_mode: ``"sitemap"`` (default) or ``"spider"``.
            max_pages: Maximum pages to crawl and inject (default: 5, max: 200).
            include_pattern: Only crawl URLs containing this substring.
            exclude_pattern: Skip URLs containing this substring.
            selector: Optional CSS selector applied to every page.
            chunk_size: Target token count per chunk (default: 512).
            overlap: Token overlap between consecutive chunks (default: 50).
            contextual_retrieval: Enable RAG 2.0 contextual enrichment.
            llm_provider: LLM provider for contextual retrieval.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name for the LLM provider.

        Returns:
            :class:`~scrapedatshi.models.AutoRagResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.
            :class:`~scrapedatshi.exceptions.ServerBusyError`: Server at capacity.

        Example::

            result = client.pipeline.autorag(
                url="https://docs.example.com",
                embedding_provider="openai",
                embedding_api_key="sk-...",
                embedding_model="text-embedding-3-small",
                vector_db="pinecone",
                vector_db_config={
                    "api_key": "pc-...",
                    "index_host": "https://my-index-abc123.svc.pinecone.io",
                },
                max_pages=20,
            )
            print(f"Crawled {result.pages_crawled} pages → {result.vectors_upserted} vectors")
            print(f"Cost: ${result.credits_used:.4f}")
        """
        embedding: dict = {"provider": embedding_provider, "api_key": embedding_api_key}
        if embedding_model:
            embedding["model"] = embedding_model

        vdb: dict = {"provider": vector_db, **vector_db_config}

        payload: dict = {
            "url": url,
            "crawl_mode": crawl_mode,
            "max_pages": max_pages,
            "embedding": embedding,
            "vector_db": vdb,
        }
        if include_pattern:
            payload["include_pattern"] = include_pattern
        if exclude_pattern:
            payload["exclude_pattern"] = exclude_pattern
        if selector:
            payload["selector"] = selector
        if chunk_size != 512:
            payload["chunk_size"] = chunk_size
        if overlap != 50:
            payload["overlap"] = overlap
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        data = self._client._post("/v1/autorag", json=payload)
        return AutoRagResult(
            root_url=data.get("root_url", url),
            crawl_mode=data.get("crawl_mode", crawl_mode),
            pages_discovered=data.get("pages_discovered", 0),
            pages_crawled=data.get("pages_crawled", 0),
            pages_failed=data.get("pages_failed", 0),
            total_chunks=data.get("total_chunks", 0),
            vectors_upserted=data.get("vectors_upserted", 0),
            total_tokens=data.get(
                "total_tokens_estimated", data.get("total_tokens", 0)
            ),
            embedding_provider=embedding_provider,
            embedding_model=data.get("embedding_model", embedding_model or ""),
            vector_db_provider=vector_db,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def autorag_async(
        self,
        url: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_config: dict,
        embedding_model: str | None = None,
        crawl_mode: str = "sitemap",
        max_pages: int = 5,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        selector: str | None = None,
        chunk_size: int = 512,
        overlap: int = 50,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> AutoRagResult:
        """Async version of :meth:`autorag`."""
        embedding: dict = {"provider": embedding_provider, "api_key": embedding_api_key}
        if embedding_model:
            embedding["model"] = embedding_model

        vdb: dict = {"provider": vector_db, **vector_db_config}

        payload: dict = {
            "url": url,
            "crawl_mode": crawl_mode,
            "max_pages": max_pages,
            "embedding": embedding,
            "vector_db": vdb,
        }
        if include_pattern:
            payload["include_pattern"] = include_pattern
        if exclude_pattern:
            payload["exclude_pattern"] = exclude_pattern
        if selector:
            payload["selector"] = selector
        if chunk_size != 512:
            payload["chunk_size"] = chunk_size
        if overlap != 50:
            payload["overlap"] = overlap
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        data = await self._client._post_async("/v1/autorag", json=payload)
        return AutoRagResult(
            root_url=data.get("root_url", url),
            crawl_mode=data.get("crawl_mode", crawl_mode),
            pages_discovered=data.get("pages_discovered", 0),
            pages_crawled=data.get("pages_crawled", 0),
            pages_failed=data.get("pages_failed", 0),
            total_chunks=data.get("total_chunks", 0),
            vectors_upserted=data.get("vectors_upserted", 0),
            total_tokens=data.get(
                "total_tokens_estimated", data.get("total_tokens", 0)
            ),
            embedding_provider=embedding_provider,
            embedding_model=data.get("embedding_model", embedding_model or ""),
            vector_db_provider=vector_db,
            contextual_retrieval_used=bool(data.get("contextual_retrieval", False)),
            contextual_retrieval_error=data.get("contextual_retrieval_error"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Vector Query ─────────────────────────────────────────────────────────

    def inspect_vectordb(
        self,
        vector_db: str,
        vector_db_config: dict,
    ) -> InspectVectorDBResult:
        """
        Read vector database metadata — dimension, vector count, and suggested
        embedding models. Use this before calling :meth:`query_vectordb` to
        confirm which embedding model was used during ingestion.

        Free — no credits charged.

        Args:
            vector_db: Vector DB provider key (e.g. ``"pinecone"``).
                See :data:`scrapedatshi.providers.VECTOR_DB_PROVIDERS` for all options.
            vector_db_config: Provider-specific configuration dict.
                Same shape as :meth:`sync`. Supports ``"USE_SAVED_CREDENTIAL"``
                for keys saved in your scrapedatshi account.

        Returns:
            :class:`~scrapedatshi.models.InspectVectorDBResult`

        Example::

            result = client.pipeline.inspect_vectordb(
                vector_db="pinecone",
                vector_db_config={
                    "api_key": "pc-...",
                    "index_host": "https://my-index.svc.pinecone.io",
                },
            )
            print(f"Dimension: {result.dimension}")
            print(f"Vectors: {result.total_vector_count}")
            for model in result.suggested_models:
                print(f"  Possible model: {model.label}")
        """
        vdb: dict = {"provider": vector_db, **vector_db_config}
        data = self._client._post("/v1/inspect-vectordb", json={"vector_db": vdb})
        return InspectVectorDBResult(
            provider=data.get("provider", vector_db),
            dimension=data.get("dimension", 0),
            total_vector_count=data.get("total_vector_count", 0),
            namespace_vector_count=data.get("namespace_vector_count"),
            namespace=data.get("namespace"),
            suggested_models=[
                SuggestedModel(**m) for m in data.get("suggested_models", [])
            ],
            dimension_known=bool(data.get("dimension_known", False)),
            note=data.get("note"),
        )

    async def inspect_vectordb_async(
        self,
        vector_db: str,
        vector_db_config: dict,
    ) -> InspectVectorDBResult:
        """Async version of :meth:`inspect_vectordb`."""
        vdb: dict = {"provider": vector_db, **vector_db_config}
        data = await self._client._post_async(
            "/v1/inspect-vectordb", json={"vector_db": vdb}
        )
        return InspectVectorDBResult(
            provider=data.get("provider", vector_db),
            dimension=data.get("dimension", 0),
            total_vector_count=data.get("total_vector_count", 0),
            namespace_vector_count=data.get("namespace_vector_count"),
            namespace=data.get("namespace"),
            suggested_models=[
                SuggestedModel(**m) for m in data.get("suggested_models", [])
            ],
            dimension_known=bool(data.get("dimension_known", False)),
            note=data.get("note"),
        )

    def query_vectordb(
        self,
        query: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        embedding_model: str,
        vector_db: str,
        vector_db_config: dict,
        top_k: int = 5,
        hybrid_search: bool = False,
        query_rewrite: dict | None = None,
    ) -> QueryVectorDBResult:
        """
        Query your vector database using natural language.

        Embeds the query using your embedding provider and runs a similarity
        search — returning the most relevant chunks from your database.

        The embedding model MUST match the model used when ingesting the data.
        Use :meth:`inspect_vectordb` first to confirm the correct model.

        Billing: $0.0002 per chunk returned (``top_k`` chunks at most).
        Example: ``top_k=5`` → $0.001 per query.

        Args:
            query: Natural language query to search for.
            embedding_provider: Embedding provider key (e.g. ``"openai"``).
                Must match the provider used during ingestion.
            embedding_api_key: API key for the embedding provider.
                Supports ``"USE_SAVED_CREDENTIAL"`` for saved keys.
            embedding_model: Embedding model name.
                **Must match the model used during ingestion exactly.**
                Use :meth:`inspect_vectordb` to confirm the correct model.
            vector_db: Vector DB provider key (e.g. ``"pinecone"``).
            vector_db_config: Provider-specific configuration dict.
                Same shape as :meth:`sync`. Supports ``"USE_SAVED_CREDENTIAL"``.
            top_k: Number of results to return (default: 5, max: 50).
                Billed at $0.0002 per chunk returned.
            hybrid_search: If True, combines dense vector search with BM25 keyword
                search using Reciprocal Rank Fusion (RRF). Improves accuracy for
                exact terms, IDs, names, and error codes. Default: False.
            query_rewrite: Optional query rewriting config. When provided, a cheap
                LLM call rewrites the raw query into a crisp, self-contained search
                query before embedding. The rewrite LLM does NOT need to match the
                embedding model. Falls back to the original query on any error.

                Format::

                    query_rewrite={
                        "llm_provider": "openai",
                        "llm_api_key": "sk-...",
                        "llm_model": "gpt-4o-mini",
                        # Optional: prior turns for pronoun resolution
                        "conversation_history": [
                            {"role": "user", "content": "Tell me about the refund policy"},
                            {"role": "assistant", "content": "The refund window is 30 days..."},
                        ],
                    }

        Returns:
            :class:`~scrapedatshi.models.QueryVectorDBResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.
            :class:`~scrapedatshi.exceptions.AuthError`: Invalid API key.

        Example::

            # Step 1: Inspect to confirm the embedding model
            inspect = client.pipeline.inspect_vectordb(
                vector_db="pinecone",
                vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
            )
            print(f"Dimension: {inspect.dimension}")
            print(f"Suggested: {[m.label for m in inspect.suggested_models]}")

            # Step 2: Query with the confirmed model
            result = client.pipeline.query_vectordb(
                query="How do I authenticate with the API?",
                embedding_provider="openai",
                embedding_api_key="sk-...",
                embedding_model="text-embedding-3-small",  # confirmed from inspect
                vector_db="pinecone",
                vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
                top_k=5,
                hybrid_search=True,  # BM25 + vector + RRF
            )
            print(f"Found {result.chunks_retrieved} results (cost: ${result.credits_used:.4f})")
            for r in result.results:
                print(f"  [{r.score:.2f}] {r.text[:100]}...")

            # With query rewriting — resolves pronouns and conversational filler
            result = client.pipeline.query_vectordb(
                query="what about the second pricing tier?",
                embedding_provider="openai",
                embedding_api_key="sk-...",
                embedding_model="text-embedding-3-small",
                vector_db="pinecone",
                vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
                query_rewrite={
                    "llm_provider": "openai",
                    "llm_api_key": "sk-...",
                    "llm_model": "gpt-4o-mini",
                },
            )
            if result.rewritten_query:
                print(f"Searched for: {result.rewritten_query}")
        """
        payload: dict = {
            "query": query,
            "top_k": top_k,
            "embedding": {
                "provider": embedding_provider,
                "api_key": embedding_api_key,
                "model": embedding_model,
            },
            "vector_db": {"provider": vector_db, **vector_db_config},
        }
        if hybrid_search:
            payload["hybrid_search"] = True
        if query_rewrite:
            payload["query_rewrite"] = query_rewrite

        data = self._client._post("/v1/query", json=payload)
        return QueryVectorDBResult(
            query=data.get("query", query),
            embedding_provider=data.get("embedding_provider", embedding_provider),
            embedding_model=data.get("embedding_model", embedding_model),
            vector_db_provider=data.get("vector_db_provider", vector_db),
            top_k_requested=data.get("top_k_requested", top_k),
            chunks_retrieved=data.get("chunks_retrieved", 0),
            hybrid_search=bool(data.get("hybrid_search", False)),
            rewritten_query=data.get("rewritten_query"),
            results=[
                QueryResult(
                    text=r.get("text", ""),
                    score=float(r.get("score", 0.0)),
                    metadata=r.get("metadata", {}),
                    rrf_score=r.get("rrf_score"),
                    hybrid_sources=r.get("hybrid_sources"),
                )
                for r in data.get("results", [])
            ],
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def query_vectordb_async(
        self,
        query: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        embedding_model: str,
        vector_db: str,
        vector_db_config: dict,
        top_k: int = 5,
        hybrid_search: bool = False,
        query_rewrite: dict | None = None,
    ) -> QueryVectorDBResult:
        """Async version of :meth:`query_vectordb`."""
        payload: dict = {
            "query": query,
            "top_k": top_k,
            "embedding": {
                "provider": embedding_provider,
                "api_key": embedding_api_key,
                "model": embedding_model,
            },
            "vector_db": {"provider": vector_db, **vector_db_config},
        }
        if hybrid_search:
            payload["hybrid_search"] = True
        if query_rewrite:
            payload["query_rewrite"] = query_rewrite

        data = await self._client._post_async("/v1/query", json=payload)
        return QueryVectorDBResult(
            query=data.get("query", query),
            embedding_provider=data.get("embedding_provider", embedding_provider),
            embedding_model=data.get("embedding_model", embedding_model),
            vector_db_provider=data.get("vector_db_provider", vector_db),
            top_k_requested=data.get("top_k_requested", top_k),
            chunks_retrieved=data.get("chunks_retrieved", 0),
            hybrid_search=bool(data.get("hybrid_search", False)),
            rewritten_query=data.get("rewritten_query"),
            results=[
                QueryResult(
                    text=r.get("text", ""),
                    score=float(r.get("score", 0.0)),
                    metadata=r.get("metadata", {}),
                    rrf_score=r.get("rrf_score"),
                    hybrid_sources=r.get("hybrid_sources"),
                )
                for r in data.get("results", [])
            ],
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── RAG Chat ─────────────────────────────────────────────────────────────

    def rag_chat(
        self,
        query: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        embedding_model: str,
        vector_db: str,
        vector_db_config: dict,
        llm_provider: str,
        llm_api_key: str,
        llm_model: str,
        top_k: int = 5,
        hybrid_search: bool = False,
        query_rewrite: bool = False,
        conversation_history: list[dict] | None = None,
    ) -> RagChatResult:
        """
        RAG Chat: embed a query, retrieve the most relevant chunks from your
        vector database, and generate a grounded LLM answer.

        The embedding model MUST match the model used when ingesting the data.
        Use :meth:`inspect_vectordb` first to confirm the correct model.

        Billing: $0.0002 per chunk retrieved (same as :meth:`query_vectordb`).
        LLM tokens are your own cost — scrapedatshi does not bill for LLM usage.

        Args:
            query: Natural language question to answer.
            embedding_provider: Embedding provider key (e.g. ``"openai"``).
                Must match the provider used during ingestion.
            embedding_api_key: API key for the embedding provider.
                Supports ``"USE_SAVED_CREDENTIAL"`` for saved keys.
            embedding_model: Embedding model name.
                **Must match the model used during ingestion exactly.**
            vector_db: Vector DB provider key (e.g. ``"pinecone"``).
            vector_db_config: Provider-specific configuration dict.
            llm_provider: LLM provider for answer generation (``"openai"``, ``"anthropic"``, or ``"gemini"``).
            llm_api_key: API key for the LLM provider.
                Supports ``"USE_SAVED_CREDENTIAL"`` for saved keys.
            llm_model: LLM model name for answer generation.
            top_k: Number of chunks to retrieve (default: 5, max: 20).
                Billed at $0.0002 per chunk retrieved.
            hybrid_search: If True, combines dense vector search with BM25 keyword
                search using Reciprocal Rank Fusion (RRF). Improves accuracy for
                exact terms, IDs, names, and error codes. Default: False.
            query_rewrite: If True, rewrites the raw query into a crisp, self-contained
                search query before embedding, using the same ``llm_provider``,
                ``llm_api_key``, and ``llm_model`` you already provided for answer
                generation. Resolves pronouns and conversational filler. Falls back
                to the original query on any error. Default: False.
            conversation_history: Optional prior conversation turns for pronoun
                resolution when ``query_rewrite=True``. Format::

                    [
                        {"role": "user", "content": "Tell me about the refund policy"},
                        {"role": "assistant", "content": "The refund window is 30 days..."},
                        {"role": "user", "content": "What about digital products?"},
                    ]

                Last 3 exchanges are used. Enables resolving "it", "that one",
                "the second", etc.

        Returns:
            :class:`~scrapedatshi.models.RagChatResult`

        Raises:
            :class:`~scrapedatshi.exceptions.InsufficientCreditsError`: Balance too low.
            :class:`~scrapedatshi.exceptions.AuthError`: Invalid API key.

        Example::

            result = client.pipeline.rag_chat(
                query="How do I authenticate with the API?",
                embedding_provider="openai",
                embedding_api_key="sk-...",
                embedding_model="text-embedding-3-small",  # must match ingestion model
                vector_db="pinecone",
                vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
                llm_provider="openai",
                llm_api_key="sk-...",
                llm_model="gpt-4o-mini",
                top_k=5,
                hybrid_search=True,   # BM25 + vector + RRF
                query_rewrite=True,   # rewrite using the same LLM
            )
            print(result.answer)
            if result.rewritten_query:
                print(f"Searched for: {result.rewritten_query}")
            print(f"Based on {result.chunks_retrieved} chunks (cost: ${result.credits_used:.4f})")
            for source in result.sources:
                print(f"  [{source.score:.2f}] {source.text[:80]}...")
        """
        payload: dict = {
            "query": query,
            "top_k": top_k,
            "embedding": {
                "provider": embedding_provider,
                "api_key": embedding_api_key,
                "model": embedding_model,
            },
            "vector_db": {"provider": vector_db, **vector_db_config},
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
            "llm_model": llm_model,
        }
        if hybrid_search:
            payload["hybrid_search"] = True
        if query_rewrite:
            payload["query_rewrite"] = True
        if conversation_history:
            payload["conversation_history"] = conversation_history

        data = self._client._post("/v1/rag-chat", json=payload)
        return RagChatResult(
            query=data.get("query", query),
            answer=data.get("answer", ""),
            embedding_provider=data.get("embedding_provider", embedding_provider),
            embedding_model=data.get("embedding_model", embedding_model),
            vector_db_provider=data.get("vector_db_provider", vector_db),
            llm_provider=data.get("llm_provider", llm_provider),
            llm_model=data.get("llm_model", llm_model),
            top_k_requested=data.get("top_k_requested", top_k),
            chunks_retrieved=data.get("chunks_retrieved", 0),
            hybrid_search=bool(data.get("hybrid_search", False)),
            rewritten_query=data.get("rewritten_query"),
            sources=[
                QueryResult(
                    text=r.get("text", ""),
                    score=float(r.get("score", 0.0)),
                    metadata=r.get("metadata", {}),
                    rrf_score=r.get("rrf_score"),
                    hybrid_sources=r.get("hybrid_sources"),
                )
                for r in data.get("sources", [])
            ],
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
            llm_error=data.get("llm_error"),
        )

    async def rag_chat_async(
        self,
        query: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        embedding_model: str,
        vector_db: str,
        vector_db_config: dict,
        llm_provider: str,
        llm_api_key: str,
        llm_model: str,
        top_k: int = 5,
        hybrid_search: bool = False,
        query_rewrite: bool = False,
        conversation_history: list[dict] | None = None,
    ) -> RagChatResult:
        """Async version of :meth:`rag_chat`."""
        payload: dict = {
            "query": query,
            "top_k": top_k,
            "embedding": {
                "provider": embedding_provider,
                "api_key": embedding_api_key,
                "model": embedding_model,
            },
            "vector_db": {"provider": vector_db, **vector_db_config},
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
            "llm_model": llm_model,
        }
        if hybrid_search:
            payload["hybrid_search"] = True
        if query_rewrite:
            payload["query_rewrite"] = True
        if conversation_history:
            payload["conversation_history"] = conversation_history

        data = await self._client._post_async("/v1/rag-chat", json=payload)
        return RagChatResult(
            query=data.get("query", query),
            answer=data.get("answer", ""),
            embedding_provider=data.get("embedding_provider", embedding_provider),
            embedding_model=data.get("embedding_model", embedding_model),
            vector_db_provider=data.get("vector_db_provider", vector_db),
            llm_provider=data.get("llm_provider", llm_provider),
            llm_model=data.get("llm_model", llm_model),
            top_k_requested=data.get("top_k_requested", top_k),
            chunks_retrieved=data.get("chunks_retrieved", 0),
            hybrid_search=bool(data.get("hybrid_search", False)),
            rewritten_query=data.get("rewritten_query"),
            sources=[
                QueryResult(
                    text=r.get("text", ""),
                    score=float(r.get("score", 0.0)),
                    metadata=r.get("metadata", {}),
                    rrf_score=r.get("rrf_score"),
                    hybrid_sources=r.get("hybrid_sources"),
                )
                for r in data.get("sources", [])
            ],
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
            llm_error=data.get("llm_error"),
        )


# ── Local crawl helpers ───────────────────────────────────────────────────────

# File extensions to skip during local crawls (same as server-side filter_urls)
_SKIP_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".gifv",
    ".webp",
    ".mp4",
    ".avi",
    ".mov",
    ".svg",
    ".css",
    ".js",
    ".zip",
    ".tar",
    ".gz",
    ".xml",
    ".json",
    ".txt",
)

# Politeness delay between page fetches (seconds)
_CRAWL_POLITENESS_DELAY = 0.5


class _LinkHarvester(HTMLParser):
    """Minimal HTML parser that extracts href values from <a> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            for attr, value in attrs:
                if attr == "href" and value:
                    self.links.append(value)


def _parse_sitemap_urls(text: str) -> list[str]:
    """
    Parse a sitemap XML string and return all <loc> URLs.
    Handles both <urlset> (regular) and <sitemapindex> (nested) formats.
    Falls back to regex extraction if XML parsing fails.
    """
    try:
        # Strip xmlns attributes to simplify namespace-safe traversal
        text_clean = re.sub(r"\s+xmlns[^>]*", "", text)
        root = ElementTree.fromstring(text_clean)
        return [loc.text.strip() for loc in root.findall(".//loc") if loc.text]
    except ElementTree.ParseError:
        # Fallback: regex extraction
        return re.findall(r"<loc>(.*?)</loc>", text)


def _fetch_sitemap_text(root_url: str) -> str | None:
    """
    Synchronously fetch a sitemap from the root domain.
    Tries /sitemap.xml, /sitemap_index.xml, then robots.txt Sitemap: directive.
    Returns the raw XML text, or None if nothing found.
    No credentials are passed — sitemaps are public assets.
    """
    import httpx as _httpx

    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {"User-Agent": "scrapedatshi-py/0.10.0 (+https://scrapedatshi.com/bot)"}

    try:
        with _httpx.Client(timeout=15.0, follow_redirects=True) as client:
            for path in ("/sitemap.xml", "/sitemap_index.xml"):
                try:
                    resp = client.get(base + path, headers=headers)
                    if resp.status_code == 200 and (
                        "<urlset" in resp.text or "<sitemapindex" in resp.text
                    ):
                        return resp.text
                except Exception:
                    continue

            # Try robots.txt for Sitemap: directive
            try:
                resp = client.get(base + "/robots.txt", headers=headers)
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        if line.lower().startswith("sitemap:"):
                            sitemap_url = line.split(":", 1)[1].strip()
                            try:
                                resp2 = client.get(sitemap_url, headers=headers)
                                if resp2.status_code == 200:
                                    return resp2.text
                            except Exception:
                                pass
            except Exception:
                pass
    except Exception:
        pass

    return None


async def _fetch_sitemap_text_async(root_url: str) -> str | None:
    """Async version of :func:`_fetch_sitemap_text`."""
    import httpx as _httpx

    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {"User-Agent": "scrapedatshi-py/0.10.0 (+https://scrapedatshi.com/bot)"}

    try:
        async with _httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for path in ("/sitemap.xml", "/sitemap_index.xml"):
                try:
                    resp = await client.get(base + path, headers=headers)
                    if resp.status_code == 200 and (
                        "<urlset" in resp.text or "<sitemapindex" in resp.text
                    ):
                        return resp.text
                except Exception:
                    continue

            try:
                resp = await client.get(base + "/robots.txt", headers=headers)
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        if line.lower().startswith("sitemap:"):
                            sitemap_url = line.split(":", 1)[1].strip()
                            try:
                                resp2 = await client.get(sitemap_url, headers=headers)
                                if resp2.status_code == 200:
                                    return resp2.text
                            except Exception:
                                pass
            except Exception:
                pass
    except Exception:
        pass

    return None


def _filter_crawl_urls(
    urls: list[str],
    root_url: str,
    include_pattern: str | None,
    exclude_pattern: str | None,
    max_pages: int,
    allow_subdomains: bool,
) -> list[str]:
    """Filter a list of discovered URLs for local crawl."""
    seen: set[str] = set()
    filtered: list[str] = []

    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)

        # Domain scope check
        if not _is_matching_domain_scope(url, root_url, allow_subdomains):
            continue

        # Pattern filters
        if include_pattern and include_pattern not in url:
            continue
        if exclude_pattern and exclude_pattern in url:
            continue

        # Skip non-content file types
        if any(url.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
            continue

        filtered.append(url)
        if len(filtered) >= max_pages:
            break

    return filtered


def _chunk_page_locally(
    client: "ScrapedatshiClient",
    page_url: str,
    html: str,
    selector: str | None,
    chunk_size: int,
    overlap: int,
    contextual_retrieval: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
) -> tuple[list[dict], float, float]:
    """
    Submit pre-fetched HTML to /v1/rag-chunk and return (chunks, credits_used, credits_remaining).
    """
    payload: dict = {"url": page_url, "html": html}
    if selector:
        payload["selector"] = selector
    if chunk_size != 512:
        payload["chunk_size"] = chunk_size
    if overlap != 50:
        payload["overlap"] = overlap
    if contextual_retrieval:
        payload["contextual_retrieval"] = True
        if llm_provider:
            payload["llm_provider"] = llm_provider
        if llm_api_key:
            payload["llm_api_key"] = llm_api_key
        if llm_model:
            payload["llm_model"] = llm_model

    try:
        data = client._post("/v1/rag-chunk", json=payload)
        return (
            data.get("chunks", []),
            float(data.get("credits_used", 0.0)),
            float(data.get("credits_remaining", 0.0)),
        )
    except Exception:
        return [], 0.0, 0.0


async def _chunk_page_locally_async(
    client: "ScrapedatshiClient",
    page_url: str,
    html: str,
    selector: str | None,
    chunk_size: int,
    overlap: int,
    contextual_retrieval: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
) -> tuple[list[dict], float, float]:
    """Async version of :func:`_chunk_page_locally`."""
    payload: dict = {"url": page_url, "html": html}
    if selector:
        payload["selector"] = selector
    if chunk_size != 512:
        payload["chunk_size"] = chunk_size
    if overlap != 50:
        payload["overlap"] = overlap
    if contextual_retrieval:
        payload["contextual_retrieval"] = True
        if llm_provider:
            payload["llm_provider"] = llm_provider
        if llm_api_key:
            payload["llm_api_key"] = llm_api_key
        if llm_model:
            payload["llm_model"] = llm_model

    try:
        data = await client._post_async("/v1/rag-chunk", json=payload)
        return (
            data.get("chunks", []),
            float(data.get("credits_used", 0.0)),
            float(data.get("credits_remaining", 0.0)),
        )
    except Exception:
        return [], 0.0, 0.0


def _crawl_locally(
    *,
    client: "ScrapedatshiClient",
    url: str,
    crawl_mode: str,
    max_pages: int,
    selector: str | None,
    include_pattern: str | None,
    exclude_pattern: str | None,
    contextual_retrieval: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
    cookies: dict | None,
    headers: dict | None,
    allow_subdomains: bool,
) -> "CrawlChunkResult":
    """
    Synchronous local crawl loop.

    Discovers URLs (sitemap or spider BFS), fetches each page on the caller's
    machine, and submits HTML to /v1/rag-chunk for chunking.

    Credential shield: cookies and headers are only sent to URLs within the
    permitted domain scope (exact match by default, subdomains if allow_subdomains=True).
    """
    all_chunks: list[dict] = []
    total_credits_used: float = 0.0
    last_credits_remaining: float = 0.0
    pages_crawled: int = 0

    if crawl_mode == "sitemap":
        # ── Sitemap mode ──────────────────────────────────────────────────────
        sitemap_text = _fetch_sitemap_text(url)
        if sitemap_text:
            discovered = _parse_sitemap_urls(sitemap_text)
        else:
            discovered = [url]  # fallback: just the root URL

        urls_to_crawl = _filter_crawl_urls(
            discovered,
            url,
            include_pattern,
            exclude_pattern,
            max_pages,
            allow_subdomains,
        )

        for page_url in urls_to_crawl:
            # Credential shield: only send creds to in-scope URLs
            send_creds = _is_matching_domain_scope(page_url, url, allow_subdomains)
            try:
                html = client._fetch_url_locally(
                    page_url,
                    cookies=cookies if send_creds else None,
                    extra_headers=headers if send_creds else None,
                )
            except Exception:
                time.sleep(_CRAWL_POLITENESS_DELAY)
                continue

            chunks, credits_used, credits_remaining = _chunk_page_locally(
                client=client,
                page_url=page_url,
                html=html,
                selector=selector,
                chunk_size=512,
                overlap=50,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )
            all_chunks.extend(chunks)
            total_credits_used += credits_used
            last_credits_remaining = credits_remaining
            pages_crawled += 1
            time.sleep(_CRAWL_POLITENESS_DELAY)

    else:
        # ── Spider mode (BFS) ─────────────────────────────────────────────────
        visited: set[str] = set()
        queue: list[str] = [url]

        while queue and pages_crawled < max_pages:
            page_url = queue.pop(0)

            # Normalize: strip fragment, trailing slash
            normalized = page_url.split("#")[0].rstrip("/")
            if not normalized:
                continue
            if normalized in visited:
                continue

            # Domain scope check for BFS queue
            if not _is_matching_domain_scope(normalized, url, allow_subdomains):
                continue

            # Pattern filters
            if include_pattern and include_pattern not in normalized:
                continue
            if exclude_pattern and exclude_pattern in normalized:
                continue

            # Skip non-content file types
            if any(normalized.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue

            visited.add(normalized)

            # Credential shield: only send creds to in-scope URLs
            send_creds = _is_matching_domain_scope(normalized, url, allow_subdomains)
            try:
                html = client._fetch_url_locally(
                    normalized,
                    cookies=cookies if send_creds else None,
                    extra_headers=headers if send_creds else None,
                )
            except Exception:
                time.sleep(_CRAWL_POLITENESS_DELAY)
                continue

            # Extract links for BFS queue
            harvester = _LinkHarvester()
            harvester.feed(html)
            for href in harvester.links:
                absolute = urljoin(normalized, href).split("#")[0].rstrip("/")
                if (
                    absolute
                    and absolute not in visited
                    and absolute not in queue
                    and _is_matching_domain_scope(absolute, url, allow_subdomains)
                    and not any(
                        absolute.lower().endswith(ext) for ext in _SKIP_EXTENSIONS
                    )
                ):
                    queue.append(absolute)

            chunks, credits_used, credits_remaining = _chunk_page_locally(
                client=client,
                page_url=normalized,
                html=html,
                selector=selector,
                chunk_size=512,
                overlap=50,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )
            all_chunks.extend(chunks)
            total_credits_used += credits_used
            last_credits_remaining = credits_remaining
            pages_crawled += 1
            time.sleep(_CRAWL_POLITENESS_DELAY)

    return CrawlChunkResult(
        chunks=all_chunks,
        total_chunks=len(all_chunks),
        pages_crawled=pages_crawled,
        source_url=url,
        contextual_retrieval_used=contextual_retrieval,
        contextual_retrieval_error=None,
        credits_used=total_credits_used,
        credits_remaining=last_credits_remaining,
    )


async def _crawl_locally_async(
    *,
    client: "ScrapedatshiClient",
    url: str,
    crawl_mode: str,
    max_pages: int,
    selector: str | None,
    include_pattern: str | None,
    exclude_pattern: str | None,
    contextual_retrieval: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
    cookies: dict | None,
    headers: dict | None,
    allow_subdomains: bool,
) -> "CrawlChunkResult":
    """
    Async local crawl loop. See :func:`_crawl_locally` for full documentation.
    """
    import asyncio as _asyncio

    all_chunks: list[dict] = []
    total_credits_used: float = 0.0
    last_credits_remaining: float = 0.0
    pages_crawled: int = 0

    if crawl_mode == "sitemap":
        # ── Sitemap mode ──────────────────────────────────────────────────────
        sitemap_text = await _fetch_sitemap_text_async(url)
        if sitemap_text:
            discovered = _parse_sitemap_urls(sitemap_text)
        else:
            discovered = [url]

        urls_to_crawl = _filter_crawl_urls(
            discovered,
            url,
            include_pattern,
            exclude_pattern,
            max_pages,
            allow_subdomains,
        )

        for page_url in urls_to_crawl:
            send_creds = _is_matching_domain_scope(page_url, url, allow_subdomains)
            try:
                html = await client._fetch_url_locally_async(
                    page_url,
                    cookies=cookies if send_creds else None,
                    extra_headers=headers if send_creds else None,
                )
            except Exception:
                await _asyncio.sleep(_CRAWL_POLITENESS_DELAY)
                continue

            chunks, credits_used, credits_remaining = await _chunk_page_locally_async(
                client=client,
                page_url=page_url,
                html=html,
                selector=selector,
                chunk_size=512,
                overlap=50,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )
            all_chunks.extend(chunks)
            total_credits_used += credits_used
            last_credits_remaining = credits_remaining
            pages_crawled += 1
            await _asyncio.sleep(_CRAWL_POLITENESS_DELAY)

    else:
        # ── Spider mode (BFS) ─────────────────────────────────────────────────
        visited: set[str] = set()
        queue: list[str] = [url]

        while queue and pages_crawled < max_pages:
            page_url = queue.pop(0)

            normalized = page_url.split("#")[0].rstrip("/")
            if not normalized:
                continue
            if normalized in visited:
                continue

            if not _is_matching_domain_scope(normalized, url, allow_subdomains):
                continue

            if include_pattern and include_pattern not in normalized:
                continue
            if exclude_pattern and exclude_pattern in normalized:
                continue

            if any(normalized.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue

            visited.add(normalized)

            send_creds = _is_matching_domain_scope(normalized, url, allow_subdomains)
            try:
                html = await client._fetch_url_locally_async(
                    normalized,
                    cookies=cookies if send_creds else None,
                    extra_headers=headers if send_creds else None,
                )
            except Exception:
                await _asyncio.sleep(_CRAWL_POLITENESS_DELAY)
                continue

            # Extract links for BFS queue
            harvester = _LinkHarvester()
            harvester.feed(html)
            for href in harvester.links:
                absolute = urljoin(normalized, href).split("#")[0].rstrip("/")
                if (
                    absolute
                    and absolute not in visited
                    and absolute not in queue
                    and _is_matching_domain_scope(absolute, url, allow_subdomains)
                    and not any(
                        absolute.lower().endswith(ext) for ext in _SKIP_EXTENSIONS
                    )
                ):
                    queue.append(absolute)

            chunks, credits_used, credits_remaining = await _chunk_page_locally_async(
                client=client,
                page_url=normalized,
                html=html,
                selector=selector,
                chunk_size=512,
                overlap=50,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )
            all_chunks.extend(chunks)
            total_credits_used += credits_used
            last_credits_remaining = credits_remaining
            pages_crawled += 1
            await _asyncio.sleep(_CRAWL_POLITENESS_DELAY)

    return CrawlChunkResult(
        chunks=all_chunks,
        total_chunks=len(all_chunks),
        pages_crawled=pages_crawled,
        source_url=url,
        contextual_retrieval_used=contextual_retrieval,
        contextual_retrieval_error=None,
        credits_used=total_credits_used,
        credits_remaining=last_credits_remaining,
    )


# ── Folder ingestion helpers ──────────────────────────────────────────────────

# Supported file extensions for ingest_folder()
_INGEST_FOLDER_EXTENSIONS = (".md", ".txt", ".json", ".yaml", ".yml")

# Keys to look for when extracting text from a JSON item (Scrapy/crawler output)
_JSON_TEXT_KEYS = ("text", "content", "html", "body", "markdown", "description")

# Max backoff sleep in seconds for 429 rate limit handling
_MAX_BACKOFF_SLEEP = 60.0


def _extract_text_from_file(
    path: Path, json_text_keys: tuple[str, ...]
) -> list[tuple[str, str]]:
    """
    Extract (text, source_url) pairs from a single file.

    For JSON files, detects whether the file is:
    - A list of crawler items (e.g. Scrapy output) → yields one entry per item
    - A single object → yields one entry for the whole file
    - A plain string → yields one entry

    Returns a list of (text, source_url) tuples.
    """
    import json as _json

    ext = path.suffix.lower()
    source_url = f"file://{path.name}"

    if ext == ".json":
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
            data = _json.loads(raw)
        except Exception:
            # Fallback: treat as plain text
            return [(path.read_text(encoding="utf-8", errors="replace"), source_url)]

        if isinstance(data, list):
            # Scrapy/crawler array — extract text from each item
            results: list[tuple[str, str]] = []
            for item in data:
                if isinstance(item, dict):
                    # Try known text keys in priority order
                    text = None
                    for key in json_text_keys:
                        val = item.get(key)
                        if val and isinstance(val, str) and val.strip():
                            text = val
                            break
                    if text is None:
                        # Fallback: JSON-encode the whole item
                        text = _json.dumps(item, ensure_ascii=False)
                    item_url = item.get("url") or item.get("link") or source_url
                    results.append((text, str(item_url)))
                elif isinstance(item, str) and item.strip():
                    results.append((item, source_url))
            return results if results else [(raw, source_url)]

        elif isinstance(data, dict):
            # Single object — try text keys, fallback to full JSON
            for key in json_text_keys:
                val = data.get(key)
                if val and isinstance(val, str) and val.strip():
                    item_url = data.get("url") or data.get("link") or source_url
                    return [(val, str(item_url))]
            return [(_json.dumps(data, ensure_ascii=False, indent=2), source_url)]

        elif isinstance(data, str):
            return [(data, source_url)]

        return [(raw, source_url)]

    elif ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, str):
                return [(data, source_url)]
            return [
                (
                    yaml.dump(data, default_flow_style=False, allow_unicode=True),
                    source_url,
                )
            ]
        except Exception:
            return [(path.read_text(encoding="utf-8", errors="replace"), source_url)]

    else:
        # .md, .txt — read as-is
        return [(path.read_text(encoding="utf-8", errors="replace"), source_url)]


def _ingest_folder_locally(
    *,
    client: "ScrapedatshiClient",
    folder_path: Path,
    embedding_provider: str,
    embedding_api_key: str,
    vector_db: str,
    vector_db_config: dict,
    embedding_model: str | None,
    embedding_endpoint: str | None,
    chunk_size: int,
    overlap: int,
    file_extensions: tuple[str, ...],
    recursive: bool,
    max_files: int | None,
    batch_delay: float,
    json_text_keys: tuple[str, ...],
) -> "IngestFolderResult":
    """
    Synchronous folder ingestion loop.

    Iterates files, extracts text (with JSON array detection), chunks via
    /v1/process-text, then embeds + injects via /v1/ingest. Includes
    exponential backoff on 429 rate limit errors.
    """
    import json as _json
    from scrapedatshi.exceptions import RateLimitError, ScrapedatshiError

    files_processed = 0
    files_failed = 0
    total_chunks = 0
    vectors_upserted = 0
    total_credits_used = 0.0
    last_credits_remaining = 0.0
    errors: list[dict] = []

    # Collect files
    if recursive:
        all_files = [
            p
            for p in folder_path.rglob("*")
            if p.is_file() and p.suffix.lower() in file_extensions
        ]
    else:
        all_files = [
            p
            for p in folder_path.iterdir()
            if p.is_file() and p.suffix.lower() in file_extensions
        ]

    all_files.sort()  # deterministic order
    if max_files is not None:
        all_files = all_files[:max_files]

    embedding_cfg = {"provider": embedding_provider, "api_key": embedding_api_key}
    if embedding_model:
        embedding_cfg["model"] = embedding_model
    if embedding_endpoint:
        embedding_cfg["endpoint"] = embedding_endpoint
    vdb_cfg = {"provider": vector_db, **vector_db_config}

    for file_path in all_files:
        try:
            text_entries = _extract_text_from_file(file_path, json_text_keys)
        except Exception as exc:
            files_failed += 1
            errors.append(
                {"file": str(file_path), "error": f"Text extraction failed: {exc}"}
            )
            continue

        for text, source_url in text_entries:
            if not text or not text.strip():
                continue

            # Step 1: Chunk the text via /v1/process-text
            chunk_payload: dict = {
                "url": source_url,
                "text": text,
                "source_type": _guess_source_type(file_path),
            }
            if chunk_size != 512:
                chunk_payload["chunk_size"] = chunk_size
            if overlap != 50:
                chunk_payload["overlap"] = overlap

            backoff = 2.0
            for attempt in range(5):
                try:
                    chunk_data = client._post("/v1/process-text", json=chunk_payload)
                    break
                except RateLimitError:
                    if attempt == 4:
                        raise
                    time.sleep(min(backoff, _MAX_BACKOFF_SLEEP))
                    backoff *= 2
            else:
                files_failed += 1
                errors.append(
                    {
                        "file": str(file_path),
                        "error": "Rate limit exceeded after retries",
                    }
                )
                continue

            chunks = chunk_data.get("chunks", [])
            if not chunks:
                continue

            # Step 2: Ingest (embed + inject) via /v1/ingest
            form_data: dict = {
                "embedding_config": _json.dumps(embedding_cfg),
                "vector_db_config": _json.dumps(vdb_cfg),
            }
            if chunk_size != 512:
                form_data["chunk_size"] = str(chunk_size)
            if overlap != 50:
                form_data["overlap"] = str(overlap)

            text_bytes = text.encode("utf-8")
            mime = (
                "text/markdown" if file_path.suffix.lower() == ".md" else "text/plain"
            )

            backoff = 2.0
            for attempt in range(5):
                try:
                    ingest_data = client._post(
                        "/v1/ingest",
                        files={"files": (file_path.name, text_bytes, mime)},
                        data=form_data,
                    )
                    break
                except RateLimitError:
                    if attempt == 4:
                        raise
                    time.sleep(min(backoff, _MAX_BACKOFF_SLEEP))
                    backoff *= 2
            else:
                files_failed += 1
                errors.append(
                    {
                        "file": str(file_path),
                        "error": "Rate limit exceeded after retries",
                    }
                )
                continue

            total_chunks += ingest_data.get("total_chunks_created", len(chunks))
            vectors_upserted += ingest_data.get("total_vectors_upserted", 0)
            total_credits_used += float(ingest_data.get("credits_used", 0.0))
            last_credits_remaining = float(ingest_data.get("credits_remaining", 0.0))

        files_processed += 1
        if batch_delay > 0:
            time.sleep(batch_delay)

    return IngestFolderResult(
        files_processed=files_processed,
        files_failed=files_failed,
        total_chunks=total_chunks,
        vectors_upserted=vectors_upserted,
        embedding_provider=embedding_provider,
        vector_db_provider=vector_db,
        credits_used=total_credits_used,
        credits_remaining=last_credits_remaining,
        errors=errors,
    )


async def _ingest_folder_locally_async(
    *,
    client: "ScrapedatshiClient",
    folder_path: Path,
    embedding_provider: str,
    embedding_api_key: str,
    vector_db: str,
    vector_db_config: dict,
    embedding_model: str | None,
    embedding_endpoint: str | None,
    chunk_size: int,
    overlap: int,
    file_extensions: tuple[str, ...],
    recursive: bool,
    max_files: int | None,
    batch_delay: float,
    json_text_keys: tuple[str, ...],
) -> "IngestFolderResult":
    """Async version of :func:`_ingest_folder_locally`."""
    import asyncio as _asyncio
    import json as _json
    from scrapedatshi.exceptions import RateLimitError

    files_processed = 0
    files_failed = 0
    total_chunks = 0
    vectors_upserted = 0
    total_credits_used = 0.0
    last_credits_remaining = 0.0
    errors: list[dict] = []

    if recursive:
        all_files = [
            p
            for p in folder_path.rglob("*")
            if p.is_file() and p.suffix.lower() in file_extensions
        ]
    else:
        all_files = [
            p
            for p in folder_path.iterdir()
            if p.is_file() and p.suffix.lower() in file_extensions
        ]

    all_files.sort()
    if max_files is not None:
        all_files = all_files[:max_files]

    embedding_cfg = {"provider": embedding_provider, "api_key": embedding_api_key}
    if embedding_model:
        embedding_cfg["model"] = embedding_model
    if embedding_endpoint:
        embedding_cfg["endpoint"] = embedding_endpoint
    vdb_cfg = {"provider": vector_db, **vector_db_config}

    for file_path in all_files:
        try:
            text_entries = await _asyncio.to_thread(
                _extract_text_from_file, file_path, json_text_keys
            )
        except Exception as exc:
            files_failed += 1
            errors.append(
                {"file": str(file_path), "error": f"Text extraction failed: {exc}"}
            )
            continue

        for text, source_url in text_entries:
            if not text or not text.strip():
                continue

            chunk_payload: dict = {
                "url": source_url,
                "text": text,
                "source_type": _guess_source_type(file_path),
            }
            if chunk_size != 512:
                chunk_payload["chunk_size"] = chunk_size
            if overlap != 50:
                chunk_payload["overlap"] = overlap

            backoff = 2.0
            for attempt in range(5):
                try:
                    chunk_data = await client._post_async(
                        "/v1/process-text", json=chunk_payload
                    )
                    break
                except RateLimitError:
                    if attempt == 4:
                        raise
                    await _asyncio.sleep(min(backoff, _MAX_BACKOFF_SLEEP))
                    backoff *= 2
            else:
                files_failed += 1
                errors.append(
                    {
                        "file": str(file_path),
                        "error": "Rate limit exceeded after retries",
                    }
                )
                continue

            chunks = chunk_data.get("chunks", [])
            if not chunks:
                continue

            form_data: dict = {
                "embedding_config": _json.dumps(embedding_cfg),
                "vector_db_config": _json.dumps(vdb_cfg),
            }
            if chunk_size != 512:
                form_data["chunk_size"] = str(chunk_size)
            if overlap != 50:
                form_data["overlap"] = str(overlap)

            text_bytes = text.encode("utf-8")
            mime = (
                "text/markdown" if file_path.suffix.lower() == ".md" else "text/plain"
            )

            backoff = 2.0
            for attempt in range(5):
                try:
                    ingest_data = await client._post_async(
                        "/v1/ingest",
                        files={"files": (file_path.name, text_bytes, mime)},
                        data=form_data,
                    )
                    break
                except RateLimitError:
                    if attempt == 4:
                        raise
                    await _asyncio.sleep(min(backoff, _MAX_BACKOFF_SLEEP))
                    backoff *= 2
            else:
                files_failed += 1
                errors.append(
                    {
                        "file": str(file_path),
                        "error": "Rate limit exceeded after retries",
                    }
                )
                continue

            total_chunks += ingest_data.get("total_chunks_created", len(chunks))
            vectors_upserted += ingest_data.get("total_vectors_upserted", 0)
            total_credits_used += float(ingest_data.get("credits_used", 0.0))
            last_credits_remaining = float(ingest_data.get("credits_remaining", 0.0))

        files_processed += 1
        if batch_delay > 0:
            await _asyncio.sleep(batch_delay)

    return IngestFolderResult(
        files_processed=files_processed,
        files_failed=files_failed,
        total_chunks=total_chunks,
        vectors_upserted=vectors_upserted,
        embedding_provider=embedding_provider,
        vector_db_provider=vector_db,
        credits_used=total_credits_used,
        credits_remaining=last_credits_remaining,
        errors=errors,
    )


# ── Response parser helpers ───────────────────────────────────────────────────


def _parse_extract_crawl_result(data: dict) -> ExtractCrawlResult:
    """Parse the /v1/extract-crawl response into an ExtractCrawlResult model."""
    raw_results = data.get("results", [])
    page_results = [
        ExtractCrawlPageResult(
            url=r.get("url", ""),
            status=r.get("status", "error"),
            extracted=r.get("extracted"),
            error=r.get("error"),
        )
        for r in raw_results
    ]

    pages_attempted = data.get("pages_attempted", len(raw_results))
    pages_extracted = data.get("pages_extracted", sum(1 for r in page_results if r.ok))
    pages_failed = data.get("pages_failed", sum(1 for r in page_results if not r.ok))

    return ExtractCrawlResult(
        results=page_results,
        pages_extracted=pages_extracted,
        pages_failed=pages_failed,
        pages_attempted=pages_attempted,
        pages_discovered=data.get("pages_discovered", pages_attempted),
        root_url=data.get("root_url", ""),
        crawl_mode=data.get("crawl_mode", "sitemap"),
        field_count=data.get("field_count", 0),
        llm_provider=data.get("llm_provider", ""),
        llm_model=data.get("llm_model", ""),
        extract_as_list=bool(data.get("extract_as_list", False)),
        job_id=data.get("job_id"),
        credits_used=float(data.get("credits_used", 0.0)),
        credits_remaining=float(data.get("credits_remaining", 0.0)),
    )
