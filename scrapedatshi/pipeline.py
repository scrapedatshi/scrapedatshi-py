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
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi.models import (
    AutoRagResult,
    ChunkResult,
    CrawlChunkResult,
    ExtractCrawlPageResult,
    ExtractCrawlResult,
    ExtractResult,
    IngestResult,
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
        Upload a local file, chunk its content, and return structured JSON chunks.
        Supports PDF, MD, TXT, YAML, YML, and JSON files.
        No embedding or vector DB required.

        Args:
            file_path: Path to the local file to upload and chunk.
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
    ) -> CrawlChunkResult:
        """
        Crawl a website, chunk all pages, and return structured JSON.

        Two crawl modes are available:
            - ``"sitemap"`` (default): Reads the site's ``sitemap.xml`` to discover URLs.
              Works best for documentation sites and blogs.
            - ``"spider"``: Follows ``<a href>`` links from the root URL.
              Works on any website — no sitemap required. More compute-intensive.

        Args:
            url: The root domain or sitemap URL to crawl.
            max_pages: Maximum number of pages to crawl.
                Sitemap mode: up to 200 pages (server hard cap).
                Spider mode: up to 200 pages (BFS link-following — more compute-intensive).
                Defaults to the server's recommended value if not specified.
            crawl_mode: ``"sitemap"`` (default) or ``"spider"``.
            selector: Optional CSS selector applied to every page.
            include_pattern: Only crawl URLs containing this substring (e.g. ``"/docs/"``).
            exclude_pattern: Skip URLs containing this substring (e.g. ``"/blog/"``).
            js_render: If True, uses a headless browser to render JS before scraping.
                Adds a surcharge per page fetched.
            contextual_retrieval: Enable RAG 2.0 contextual enrichment.
                Adds a surcharge per URL crawled.
            llm_provider: LLM provider for contextual retrieval.
                See :data:`scrapedatshi.providers.LLM_PROVIDERS` for supported providers.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name.

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
        """
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
    ) -> CrawlChunkResult:
        """Async version of :meth:`crawl`."""
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
