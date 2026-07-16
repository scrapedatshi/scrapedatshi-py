"""
scrapedatshi.pipeline._query
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Vector DB query methods: inspect_vectordb, query_vectordb, rag_chat.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi.models import (
    InspectVectorDBResult,
    QueryResult,
    QueryVectorDBResult,
    RagChatResult,
    SuggestedModel,
)


class QueryMixin:
    """Mixin providing inspect_vectordb, query_vectordb, and rag_chat methods."""

    _client: "ScrapedatshiClient"

    # ── Inspect Vector DB ─────────────────────────────────────────────────────

    def inspect_vectordb(
        self,
        vector_db: str,
        vector_db_config: dict,
    ) -> InspectVectorDBResult:
        """
        Read vector database metadata — dimension, vector count, and suggested
        embedding models. Free — no credits charged.
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

    # ── Query Vector DB ───────────────────────────────────────────────────────

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
    ) -> QueryVectorDBResult:
        """
        Query your vector database using natural language.
        Billing: $0.0002 per chunk returned.
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
        data = self._client._post("/v1/query", json=payload)
        return QueryVectorDBResult(
            query=data.get("query", query),
            embedding_provider=data.get("embedding_provider", embedding_provider),
            embedding_model=data.get("embedding_model", embedding_model),
            vector_db_provider=data.get("vector_db_provider", vector_db),
            top_k_requested=data.get("top_k_requested", top_k),
            chunks_retrieved=data.get("chunks_retrieved", 0),
            results=[
                QueryResult(
                    text=r.get("text", ""),
                    score=float(r.get("score", 0.0)),
                    metadata=r.get("metadata", {}),
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
        data = await self._client._post_async("/v1/query", json=payload)
        return QueryVectorDBResult(
            query=data.get("query", query),
            embedding_provider=data.get("embedding_provider", embedding_provider),
            embedding_model=data.get("embedding_model", embedding_model),
            vector_db_provider=data.get("vector_db_provider", vector_db),
            top_k_requested=data.get("top_k_requested", top_k),
            chunks_retrieved=data.get("chunks_retrieved", 0),
            results=[
                QueryResult(
                    text=r.get("text", ""),
                    score=float(r.get("score", 0.0)),
                    metadata=r.get("metadata", {}),
                )
                for r in data.get("results", [])
            ],
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── RAG Chat ──────────────────────────────────────────────────────────────

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
    ) -> RagChatResult:
        """
        RAG Chat: embed a query, retrieve the most relevant chunks from your
        vector database, and generate a grounded LLM answer.
        Billing: $0.0002 per chunk retrieved. LLM tokens are your own cost.
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
            sources=[
                QueryResult(
                    text=r.get("text", ""),
                    score=float(r.get("score", 0.0)),
                    metadata=r.get("metadata", {}),
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
            sources=[
                QueryResult(
                    text=r.get("text", ""),
                    score=float(r.get("score", 0.0)),
                    metadata=r.get("metadata", {}),
                )
                for r in data.get("sources", [])
            ],
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
            llm_error=data.get("llm_error"),
        )
