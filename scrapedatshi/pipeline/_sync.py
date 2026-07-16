"""
scrapedatshi.pipeline._sync
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Sync and AutoRAG methods.

Full pipeline: scrape/crawl → chunk → embed → inject into vector DB.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi.models import AutoRagResult, SyncResult


class SyncMixin:
    """Mixin providing sync and autorag methods."""

    _client: "ScrapedatshiClient"

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

    # ── AutoRAG — Full Crawl Pipeline ─────────────────────────────────────────

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
