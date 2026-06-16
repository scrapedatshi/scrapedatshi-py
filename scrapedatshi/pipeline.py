"""
scrapedatshi.pipeline
~~~~~~~~~~~~~~~~~~~~~
PipelineNamespace — all pipeline methods, both sync and async.

Accessed via client.pipeline.*

Sync methods use httpx.Client (blocking).
Async methods use httpx.AsyncClient (non-blocking, for asyncio).
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi.models import (
    ChunkResult,
    CrawlChunkResult,
    IngestResult,
    SyncResult,
)


class PipelineNamespace:
    """
    All pipeline operations, accessible via ``client.pipeline``.

    Chunk-to-JSON (no embedding required):
        - chunk_url()        / chunk_url_async()
        - chunk_file()       / chunk_file_async()
        - crawl()            / crawl_async()

    Full Pipeline (embed + vector DB inject, Pro/Enterprise only):
        - sync()             / sync_async()
        - ingest()           / ingest_async()
    """

    def __init__(self, client: "ScrapedatshiClient") -> None:
        self._client = client

    # ── Chunk to JSON — URL ───────────────────────────────────────────────────

    def chunk_url(
        self,
        url: str,
        *,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> ChunkResult:
        """
        Scrape a URL, chunk the content, and return structured JSON chunks.
        No embedding or vector DB required — works on all tiers.

        Args:
            url: The web URL to scrape and chunk.
            contextual_retrieval: Enable RAG 2.0 contextual enrichment (Basic+ tier).
            llm_provider: LLM provider for contextual retrieval (e.g. ``"openai"``).
            llm_api_key: API key for the LLM provider.
            llm_model: Model name (e.g. ``"gpt-4o-mini"``).

        Returns:
            :class:`~scrapedatshi.models.ChunkResult`

        Example::

            result = client.pipeline.chunk_url("https://docs.example.com")
            for chunk in result.chunks:
                print(chunk.content)
        """
        payload: dict = {"url": url}
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        data = self._client._post("/v1/rag-chunk", json=payload)
        return ChunkResult(
            chunks=data.get("chunks", []),
            total_chunks=data.get("total_chunks", len(data.get("chunks", []))),
            source=url,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    async def chunk_url_async(
        self,
        url: str,
        *,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> ChunkResult:
        """Async version of :meth:`chunk_url`."""
        payload: dict = {"url": url}
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
            total_chunks=data.get("total_chunks", len(data.get("chunks", []))),
            source=url,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    # ── Chunk to JSON — File ──────────────────────────────────────────────────

    def chunk_file(
        self,
        file_path: str | Path,
        *,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> ChunkResult:
        """
        Upload a local file, chunk its content, and return structured JSON chunks.
        Supports PDF, DOCX, TXT, MD, and HTML files.
        No embedding or vector DB required — works on all tiers.

        Args:
            file_path: Path to the local file to upload and chunk.
            contextual_retrieval: Enable RAG 2.0 contextual enrichment (Basic+ tier).
            llm_provider: LLM provider for contextual retrieval.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name.

        Returns:
            :class:`~scrapedatshi.models.ChunkResult`

        Example::

            result = client.pipeline.chunk_file("./docs/manual.pdf")
            print(f"Got {result.total_chunks} chunks from {result.source}")
        """
        path = Path(file_path)
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        form_data: dict = {}
        if contextual_retrieval:
            form_data["contextual_retrieval"] = "true"
            if llm_provider:
                form_data["llm_provider"] = llm_provider
            if llm_api_key:
                form_data["llm_api_key"] = llm_api_key
            if llm_model:
                form_data["llm_model"] = llm_model

        with open(path, "rb") as f:
            files = {"file": (path.name, f, mime_type)}
            data = self._client._post("/v1/ingest-chunk", files=files, data=form_data)

        return ChunkResult(
            chunks=data.get("chunks", []),
            total_chunks=data.get("total_chunks", len(data.get("chunks", []))),
            source=path.name,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    async def chunk_file_async(
        self,
        file_path: str | Path,
        *,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> ChunkResult:
        """Async version of :meth:`chunk_file`."""
        path = Path(file_path)
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        form_data: dict = {}
        if contextual_retrieval:
            form_data["contextual_retrieval"] = "true"
            if llm_provider:
                form_data["llm_provider"] = llm_provider
            if llm_api_key:
                form_data["llm_api_key"] = llm_api_key
            if llm_model:
                form_data["llm_model"] = llm_model

        with open(path, "rb") as f:
            files = {"file": (path.name, f, mime_type)}
            data = await self._client._post_async(
                "/v1/ingest-chunk", files=files, data=form_data
            )

        return ChunkResult(
            chunks=data.get("chunks", []),
            total_chunks=data.get("total_chunks", len(data.get("chunks", []))),
            source=path.name,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    # ── Chunk to JSON — Sitemap Crawl ─────────────────────────────────────────

    def crawl(
        self,
        url: str,
        *,
        max_pages: int | None = None,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> CrawlChunkResult:
        """
        Crawl a website via its sitemap, chunk all pages, and return structured JSON.
        Requires Basic tier or higher.

        Args:
            url: The root domain or sitemap URL to crawl.
            max_pages: Maximum number of pages to crawl (capped by your tier limit).
            contextual_retrieval: Enable RAG 2.0 contextual enrichment (Basic+ tier).
            llm_provider: LLM provider for contextual retrieval.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name.

        Returns:
            :class:`~scrapedatshi.models.CrawlChunkResult`

        Example::

            result = client.pipeline.crawl("https://example.com", max_pages=10)
            print(f"Crawled {result.pages_crawled} pages → {result.total_chunks} chunks")
        """
        payload: dict = {"url": url}
        if max_pages is not None:
            payload["max_pages"] = max_pages
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        data = self._client._post("/v1/crawl-chunk", json=payload)
        return CrawlChunkResult(
            chunks=data.get("chunks", []),
            total_chunks=data.get("total_chunks", len(data.get("chunks", []))),
            pages_crawled=data.get("pages_crawled", 0),
            source_url=url,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    async def crawl_async(
        self,
        url: str,
        *,
        max_pages: int | None = None,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> CrawlChunkResult:
        """Async version of :meth:`crawl`."""
        payload: dict = {"url": url}
        if max_pages is not None:
            payload["max_pages"] = max_pages
        if contextual_retrieval:
            payload["contextual_retrieval"] = True
            if llm_provider:
                payload["llm_provider"] = llm_provider
            if llm_api_key:
                payload["llm_api_key"] = llm_api_key
            if llm_model:
                payload["llm_model"] = llm_model

        data = await self._client._post_async("/v1/crawl-chunk", json=payload)
        return CrawlChunkResult(
            chunks=data.get("chunks", []),
            total_chunks=data.get("total_chunks", len(data.get("chunks", []))),
            pages_crawled=data.get("pages_crawled", 0),
            source_url=url,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    # ── Full Pipeline — URL Sync ──────────────────────────────────────────────

    def sync(
        self,
        url: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_api_key: str,
        index_name: str,
        embedding_model: str | None = None,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> SyncResult:
        """
        Full pipeline: scrape a URL, embed chunks, and inject into a vector DB.
        Requires Pro tier or higher.

        Args:
            url: The web URL to scrape, embed, and inject.
            embedding_provider: Embedding provider (``"openai"``, ``"cohere"``, etc.).
            embedding_api_key: API key for the embedding provider.
            vector_db: Vector DB provider (``"pinecone"``, ``"qdrant"``, ``"weaviate"``).
            vector_db_api_key: API key for the vector DB.
            index_name: Target index / collection name in the vector DB.
            embedding_model: Optional model override (e.g. ``"text-embedding-3-small"``).
            contextual_retrieval: Enable RAG 2.0 contextual enrichment.
            llm_provider: LLM provider for contextual retrieval.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name.

        Returns:
            :class:`~scrapedatshi.models.SyncResult`

        Example::

            result = client.pipeline.sync(
                url="https://docs.example.com",
                embedding_provider="openai",
                embedding_api_key="sk-...",
                vector_db="pinecone",
                vector_db_api_key="pc-...",
                index_name="my-docs",
            )
            print(f"Upserted {result.vectors_upserted} vectors")
        """
        payload: dict = {
            "url": url,
            "embedding_provider": embedding_provider,
            "embedding_api_key": embedding_api_key,
            "vector_db": vector_db,
            "vector_db_api_key": vector_db_api_key,
            "index_name": index_name,
        }
        if embedding_model:
            payload["embedding_model"] = embedding_model
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
            total_tokens=data.get("total_tokens", 0),
            embedding_provider=embedding_provider,
            vector_db_provider=vector_db,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    async def sync_async(
        self,
        url: str,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_api_key: str,
        index_name: str,
        embedding_model: str | None = None,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> SyncResult:
        """Async version of :meth:`sync`."""
        payload: dict = {
            "url": url,
            "embedding_provider": embedding_provider,
            "embedding_api_key": embedding_api_key,
            "vector_db": vector_db,
            "vector_db_api_key": vector_db_api_key,
            "index_name": index_name,
        }
        if embedding_model:
            payload["embedding_model"] = embedding_model
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
            total_tokens=data.get("total_tokens", 0),
            embedding_provider=embedding_provider,
            vector_db_provider=vector_db,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    # ── Full Pipeline — File Ingest ───────────────────────────────────────────

    def ingest(
        self,
        file_path: str | Path,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_api_key: str,
        index_name: str,
        embedding_model: str | None = None,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> IngestResult:
        """
        Full pipeline: upload a local file, embed chunks, and inject into a vector DB.
        Requires Pro tier or higher.

        Args:
            file_path: Path to the local file to upload, embed, and inject.
            embedding_provider: Embedding provider (``"openai"``, ``"cohere"``, etc.).
            embedding_api_key: API key for the embedding provider.
            vector_db: Vector DB provider (``"pinecone"``, ``"qdrant"``, ``"weaviate"``).
            vector_db_api_key: API key for the vector DB.
            index_name: Target index / collection name in the vector DB.
            embedding_model: Optional model override.
            contextual_retrieval: Enable RAG 2.0 contextual enrichment.
            llm_provider: LLM provider for contextual retrieval.
            llm_api_key: API key for the LLM provider.
            llm_model: Model name.

        Returns:
            :class:`~scrapedatshi.models.IngestResult`
        """
        path = Path(file_path)
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        form_data: dict = {
            "embedding_provider": embedding_provider,
            "embedding_api_key": embedding_api_key,
            "vector_db": vector_db,
            "vector_db_api_key": vector_db_api_key,
            "index_name": index_name,
        }
        if embedding_model:
            form_data["embedding_model"] = embedding_model
        if contextual_retrieval:
            form_data["contextual_retrieval"] = "true"
            if llm_provider:
                form_data["llm_provider"] = llm_provider
            if llm_api_key:
                form_data["llm_api_key"] = llm_api_key
            if llm_model:
                form_data["llm_model"] = llm_model

        with open(path, "rb") as f:
            files = {"file": (path.name, f, mime_type)}
            data = self._client._post("/v1/ingest", files=files, data=form_data)

        return IngestResult(
            status=data.get("status", "success"),
            chunks_created=data.get("chunks_created", 0),
            vectors_upserted=data.get("vectors_upserted", 0),
            total_tokens=data.get("total_tokens", 0),
            embedding_provider=embedding_provider,
            vector_db_provider=vector_db,
            filename=path.name,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )

    async def ingest_async(
        self,
        file_path: str | Path,
        *,
        embedding_provider: str,
        embedding_api_key: str,
        vector_db: str,
        vector_db_api_key: str,
        index_name: str,
        embedding_model: str | None = None,
        contextual_retrieval: bool = False,
        llm_provider: str | None = None,
        llm_api_key: str | None = None,
        llm_model: str | None = None,
    ) -> IngestResult:
        """Async version of :meth:`ingest`."""
        path = Path(file_path)
        mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"

        form_data: dict = {
            "embedding_provider": embedding_provider,
            "embedding_api_key": embedding_api_key,
            "vector_db": vector_db,
            "vector_db_api_key": vector_db_api_key,
            "index_name": index_name,
        }
        if embedding_model:
            form_data["embedding_model"] = embedding_model
        if contextual_retrieval:
            form_data["contextual_retrieval"] = "true"
            if llm_provider:
                form_data["llm_provider"] = llm_provider
            if llm_api_key:
                form_data["llm_api_key"] = llm_api_key
            if llm_model:
                form_data["llm_model"] = llm_model

        with open(path, "rb") as f:
            files = {"file": (path.name, f, mime_type)}
            data = await self._client._post_async(
                "/v1/ingest", files=files, data=form_data
            )

        return IngestResult(
            status=data.get("status", "success"),
            chunks_created=data.get("chunks_created", 0),
            vectors_upserted=data.get("vectors_upserted", 0),
            total_tokens=data.get("total_tokens", 0),
            embedding_provider=embedding_provider,
            vector_db_provider=vector_db,
            filename=path.name,
            contextual_retrieval_used=data.get("contextual_retrieval_used", False),
        )
