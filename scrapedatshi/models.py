"""
scrapedatshi.models
~~~~~~~~~~~~~~~~~~~
Pydantic response models for all scrapedatshi API endpoints.

All models use strict typing so IDEs can provide full IntelliSense
autocomplete on response objects.

Every response includes ``credits_used`` and ``credits_remaining`` fields
so you can track spend programmatically without hitting the billing API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Shared primitives ─────────────────────────────────────────────────────────


class Chunk(BaseModel):
    """A single text chunk produced by the pipeline.

    The server returns the chunk text as ``"text"`` in its JSON payload.
    This model maps that field to the public ``content`` attribute via an
    alias so existing user code (``chunk.content``) continues to work
    without any changes.

    When ``contextual_retrieval=True`` is used, two additional fields are
    populated:

    - ``original_text``: the raw chunk text before enrichment
    - ``context``: the LLM-generated per-chunk context string
    - ``content`` (``text``): the combined string ``"Context: {context}\\n\\n{original_text}"``
    """

    model_config = ConfigDict(populate_by_name=True)

    content: str = Field(
        ...,
        alias="text",
        description="The chunk text content (server field: ``text``). When contextual_retrieval=True, this is the combined 'Context: ...\\n\\n{original_text}' string.",
    )
    token_estimate: int = Field(
        ..., description="Estimated token count for this chunk."
    )
    original_text: str | None = Field(
        None,
        description=(
            "The raw chunk text before contextual enrichment. "
            "Only set when contextual_retrieval=True and CR succeeded for this chunk."
        ),
    )
    context: str | None = Field(
        None,
        description=(
            "The LLM-generated per-chunk context string prepended before embedding. "
            "Includes document identity, section identity, and specific entities. "
            "Only set when contextual_retrieval=True and CR succeeded for this chunk."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata attached to this chunk (source URL, page number, etc.).",
    )

    def __len__(self) -> int:
        return len(self.content)

    def __repr__(self) -> str:
        preview = self.content[:60].replace("\n", " ")
        return f"Chunk(tokens={self.token_estimate}, content={preview!r}...)"


# ── Chunk to JSON responses ───────────────────────────────────────────────────


class ChunkResult(BaseModel):
    """
    Response from chunk_url(), chunk_file(), or crawl() in Chunk-to-JSON mode.

    Example::

        result = client.pipeline.chunk_url("https://docs.example.com")
        for chunk in result.chunks:
            print(chunk.content)
        print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")
    """

    chunks: list[Chunk] = Field(
        ..., description="List of text chunks extracted from the source."
    )
    total_chunks: int = Field(..., description="Total number of chunks returned.")
    source: str = Field(
        ..., description="The source URL or filename that was processed."
    )
    contextual_retrieval_used: bool = Field(
        False,
        description="Whether Contextual Retrieval (RAG 2.0) was applied to enrich chunks.",
    )
    contextual_retrieval_error: str | None = Field(
        None,
        description=(
            "Error message if contextual retrieval failed (e.g. invalid LLM key or unsupported model). "
            "Chunks are still returned without context enrichment when this is set."
        ),
    )
    content_truncated: bool = Field(
        False,
        description=(
            "True if the source content exceeded the maximum content size (~75,000 words) "
            "and was automatically truncated before chunking."
        ),
    )
    credits_used: float = Field(
        0.0,
        description="Credits deducted for this request (URL fetch fee + chunk fee).",
    )
    credits_remaining: float = Field(
        0.0,
        description="Account credit balance after this request.",
    )

    def __len__(self) -> int:
        return self.total_chunks

    def __repr__(self) -> str:
        return f"ChunkResult(total_chunks={self.total_chunks}, source={self.source!r}, credits_used={self.credits_used:.4f})"


class CrawlChunkResult(BaseModel):
    """
    Response from crawl() in Chunk-to-JSON mode.
    Contains chunks from all crawled pages combined.

    Example::

        result = client.pipeline.crawl("https://example.com/sitemap.xml", max_pages=10)
        print(f"Crawled {result.pages_crawled} pages → {result.total_chunks} chunks")
        print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")
    """

    chunks: list[Chunk] = Field(..., description="All chunks from all crawled pages.")
    total_chunks: int = Field(
        ..., description="Total number of chunks across all pages."
    )
    pages_crawled: int = Field(..., description="Number of pages successfully crawled.")
    source_url: str = Field(
        ..., description="The root URL or sitemap URL that was crawled."
    )
    contextual_retrieval_used: bool = Field(False)
    contextual_retrieval_error: str | None = Field(
        None,
        description=(
            "Error message if contextual retrieval failed (e.g. invalid LLM key or unsupported model). "
            "Chunks are still returned without context enrichment when this is set."
        ),
    )
    credits_used: float = Field(
        0.0,
        description="Credits deducted for this request (URL fetch fees + chunk fees).",
    )
    credits_remaining: float = Field(
        0.0,
        description="Account credit balance after this request.",
    )

    def __len__(self) -> int:
        return self.total_chunks

    def __repr__(self) -> str:
        return (
            f"CrawlChunkResult(pages={self.pages_crawled}, "
            f"total_chunks={self.total_chunks}, source={self.source_url!r}, "
            f"credits_used={self.credits_used:.4f})"
        )


# ── Full Pipeline responses ───────────────────────────────────────────────────


class SyncResult(BaseModel):
    """
    Response from pipeline.sync() — URL-based full pipeline (embed + vector DB inject).

    Example::

        result = client.pipeline.sync(
            url="https://docs.example.com",
            embedding_provider="openai",
            embedding_api_key="sk-...",
            vector_db="pinecone",
            vector_db_api_key="...",
            index_name="my-index",
        )
        print(f"Upserted {result.vectors_upserted} vectors")
        print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")
    """

    status: str = Field(..., description="'success' or 'error'.")
    chunks_created: int = Field(..., description="Number of text chunks generated.")
    vectors_upserted: int = Field(
        ..., description="Number of vectors written to the vector DB."
    )
    total_tokens: int = Field(
        ..., description="Total tokens processed across all chunks."
    )
    embedding_provider: str = Field(
        ..., description="Embedding provider used (e.g. 'openai')."
    )
    vector_db_provider: str = Field(
        ..., description="Vector DB provider used (e.g. 'pinecone')."
    )
    contextual_retrieval_used: bool = Field(False)
    contextual_retrieval_error: str | None = Field(
        None,
        description=(
            "Error message if contextual retrieval failed (e.g. invalid LLM key or unsupported model). "
            "Vectors are still upserted without context enrichment when this is set."
        ),
    )
    credits_used: float = Field(
        0.0,
        description="Credits deducted for this request (URL fetch + chunk fees + injection fees).",
    )
    credits_remaining: float = Field(
        0.0,
        description="Account credit balance after this request.",
    )

    def __repr__(self) -> str:
        return (
            f"SyncResult(status={self.status!r}, chunks={self.chunks_created}, "
            f"vectors={self.vectors_upserted}, tokens={self.total_tokens}, "
            f"credits_used={self.credits_used:.4f})"
        )


class IngestResult(BaseModel):
    """
    Response from pipeline.ingest() — file-based full pipeline (embed + vector DB inject).

    Example::

        result = client.pipeline.ingest(
            file_path="./docs/manual.pdf",
            embedding_provider="openai",
            embedding_api_key="sk-...",
            vector_db="pinecone",
            vector_db_api_key="...",
            index_name="my-index",
        )
        print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")
    """

    status: str
    chunks_created: int
    vectors_upserted: int
    total_tokens: int
    embedding_provider: str
    vector_db_provider: str
    filename: str = Field("", description="Original filename that was ingested.")
    contextual_retrieval_used: bool = Field(False)
    contextual_retrieval_error: str | None = Field(
        None,
        description=(
            "Error message if contextual retrieval failed (e.g. invalid LLM key or unsupported model). "
            "Vectors are still upserted without context enrichment when this is set."
        ),
    )
    credits_used: float = Field(
        0.0,
        description="Credits deducted for this request (file parse + chunk fees + injection fees).",
    )
    credits_remaining: float = Field(
        0.0,
        description="Account credit balance after this request.",
    )

    def __repr__(self) -> str:
        return (
            f"IngestResult(status={self.status!r}, file={self.filename!r}, "
            f"chunks={self.chunks_created}, vectors={self.vectors_upserted}, "
            f"credits_used={self.credits_used:.4f})"
        )


# ── Schema Extract response ───────────────────────────────────────────────────


class ExtractResult(BaseModel):
    """
    Response from pipeline.extract() — structured data extracted from a URL using an LLM.

    The ``extracted`` field contains either a single dict (default) or a list of dicts
    when ``extract_as_list=True`` was used.

    Example::

        result = client.pipeline.extract(
            url="https://example.com/products",
            schema={"title": "string — product name", "price": "number — price in USD"},
            llm_provider="openai",
            llm_api_key="sk-...",
        )
        print(result.extracted)
        # → {"title": "Widget Pro", "price": 29.99}

        # List mode — extract all matching items on the page
        result = client.pipeline.extract(
            url="https://example.com/products",
            schema={"title": "string — product name", "price": "number — price in USD"},
            llm_provider="openai",
            llm_api_key="sk-...",
            extract_as_list=True,
        )
        print(result.extracted)
        # → [{"title": "Widget Pro", "price": 29.99}, {"title": "Widget Lite", "price": 9.99}]
        print(f"Extracted {result.item_count} items")
        print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")
    """

    extracted: Any = Field(
        ...,
        description=(
            "Extracted data matching your schema. "
            "A dict when extract_as_list=False (default), "
            "or a list[dict] when extract_as_list=True."
        ),
    )
    field_count: int = Field(
        ..., description="Number of schema fields that were defined."
    )
    item_count: int | None = Field(
        None,
        description="Number of items extracted (only set when extract_as_list=True).",
    )
    url: str = Field(..., description="The URL that was scraped and extracted from.")
    llm_provider: str = Field(..., description="LLM provider used for extraction.")
    llm_model: str = Field(..., description="LLM model used for extraction.")
    schema_fields: list[str] = Field(
        default_factory=list,
        description="List of field names defined in the schema.",
    )
    js_render: bool = Field(
        False, description="Whether JS rendering was used for this request."
    )
    content_warning: str | None = Field(
        None,
        description=(
            "Warning message if the page content was thin or potentially incomplete "
            "(e.g. JS-heavy page that may need js_render=True)."
        ),
    )
    credits_used: float = Field(
        0.0,
        description="Credits deducted for this request (fetch fee + orchestration + per-field fee).",
    )
    credits_remaining: float = Field(
        0.0,
        description="Account credit balance after this request.",
    )

    @property
    def is_list(self) -> bool:
        """True if the extracted result is a list (extract_as_list mode)."""
        return isinstance(self.extracted, list)

    def __len__(self) -> int:
        if isinstance(self.extracted, list):
            return len(self.extracted)
        return 1

    def __repr__(self) -> str:
        mode = f"list[{self.item_count}]" if self.is_list else "object"
        return (
            f"ExtractResult(url={self.url!r}, fields={self.field_count}, "
            f"mode={mode}, credits_used={self.credits_used:.4f})"
        )


# ── Extract Crawl responses ───────────────────────────────────────────────────


class ExtractCrawlPageResult(BaseModel):
    """
    Result for a single page within an :class:`ExtractCrawlResult`.

    ``status`` is ``"ok"`` when extraction succeeded, ``"error"`` when it failed.
    Failed pages do not abort the batch — they return an error message and the
    crawl continues to the next page.
    """

    url: str = Field(..., description="The URL that was scraped and extracted from.")
    status: str = Field(
        ...,
        description="'ok' if extraction succeeded, 'error' if it failed.",
    )
    extracted: Any = Field(
        None,
        description=(
            "Extracted data matching your schema. "
            "A dict when extract_as_list=False (default), "
            "or a list[dict] when extract_as_list=True. "
            "None when status='error'."
        ),
    )
    error: str | None = Field(
        None,
        description="Error message when status='error'. None when status='ok'.",
    )

    @property
    def ok(self) -> bool:
        """True if this page was successfully extracted."""
        return self.status == "ok"

    def __repr__(self) -> str:
        if self.ok:
            return f"ExtractCrawlPageResult(url={self.url!r}, status='ok')"
        return f"ExtractCrawlPageResult(url={self.url!r}, status='error', error={self.error!r})"


class ExtractCrawlResult(BaseModel):
    """
    Response from extract_crawl() — multi-page schema extraction via site crawl.

    Each page in ``results`` is processed independently. Failed pages return an
    error object without aborting the batch. Only successfully extracted pages
    are billed.

    Example::

        result = client.pipeline.extract_crawl(
            url="https://example.com/products",
            schema={
                "title": "string — the product name",
                "price": "number — the price in USD",
            },
            llm_provider="openai",
            llm_api_key="sk-...",
            max_pages=20,
        )

        print(f"Extracted {result.pages_extracted}/{result.pages_attempted} pages")
        print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")

        for page in result.results:
            if page.ok:
                print(f"  {page.url}: {page.extracted}")
            else:
                print(f"  {page.url}: ERROR — {page.error}")

        # Access only successful results
        successful = result.successful_results
        print(f"Got {len(successful)} successful extractions")
    """

    results: list[ExtractCrawlPageResult] = Field(
        ...,
        description="Per-page extraction results. Each item has url, status, extracted, and error.",
    )
    pages_extracted: int = Field(
        ..., description="Number of pages successfully extracted."
    )
    pages_failed: int = Field(
        ..., description="Number of pages that failed to extract."
    )
    pages_attempted: int = Field(
        ..., description="Total number of pages attempted (extracted + failed)."
    )
    pages_discovered: int = Field(
        ..., description="Total URLs discovered in the sitemap or spider crawl."
    )
    root_url: str = Field(..., description="The root URL that was crawled.")
    crawl_mode: str = Field(..., description="Crawl mode used: 'sitemap' or 'spider'.")
    field_count: int = Field(..., description="Number of schema fields defined.")
    llm_provider: str = Field(..., description="LLM provider used for extraction.")
    llm_model: str = Field(..., description="LLM model used for extraction.")
    extract_as_list: bool = Field(
        False,
        description="Whether list extraction mode was used.",
    )
    job_id: str | None = Field(
        None,
        description=(
            "Persistent job ID for this crawl. Use GET /portal/jobs/{job_id} "
            "to retrieve results after the fact."
        ),
    )
    credits_used: float = Field(
        0.0,
        description="Total credits deducted (only for successfully extracted pages).",
    )
    credits_remaining: float = Field(
        0.0,
        description="Account credit balance after this request.",
    )

    @property
    def successful_results(self) -> list[ExtractCrawlPageResult]:
        """Returns only the successfully extracted page results."""
        return [r for r in self.results if r.ok]

    @property
    def failed_results(self) -> list[ExtractCrawlPageResult]:
        """Returns only the failed page results."""
        return [r for r in self.results if not r.ok]

    def __len__(self) -> int:
        return self.pages_extracted

    def __repr__(self) -> str:
        return (
            f"ExtractCrawlResult("
            f"pages_extracted={self.pages_extracted}, "
            f"pages_failed={self.pages_failed}, "
            f"root_url={self.root_url!r}, "
            f"credits_used={self.credits_used:.4f})"
        )


# ── AutoRAG response ──────────────────────────────────────────────────────────


class AutoRagResult(BaseModel):
    """
    Response from pipeline.autorag() — full AutoRAG pipeline:
    crawl a domain → chunk every page → embed → inject into vector DB.

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
            max_pages=10,
        )
        print(f"Crawled {result.pages_crawled} pages → {result.vectors_upserted} vectors")
        print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")
    """

    root_url: str = Field(..., description="The root URL that was crawled.")
    crawl_mode: str = Field(..., description="Crawl mode used: 'sitemap' or 'spider'.")
    pages_discovered: int = Field(
        ..., description="Total URLs discovered in the sitemap or spider crawl."
    )
    pages_crawled: int = Field(
        ..., description="Number of pages successfully crawled and chunked."
    )
    pages_failed: int = Field(..., description="Number of pages that failed to crawl.")
    total_chunks: int = Field(
        ..., description="Total number of chunks generated across all pages."
    )
    vectors_upserted: int = Field(
        ..., description="Number of vectors written to the vector DB."
    )
    total_tokens: int = Field(
        ..., description="Total tokens estimated across all chunks."
    )
    embedding_provider: str = Field(
        ..., description="Embedding provider used (e.g. 'openai')."
    )
    embedding_model: str = Field(..., description="Embedding model used.")
    vector_db_provider: str = Field(
        ..., description="Vector DB provider used (e.g. 'pinecone')."
    )
    contextual_retrieval_used: bool = Field(
        False,
        description="Whether Contextual Retrieval (RAG 2.0) was applied.",
    )
    contextual_retrieval_error: str | None = Field(
        None,
        description=(
            "Error message if contextual retrieval failed. "
            "Vectors are still upserted without context enrichment when this is set."
        ),
    )
    credits_used: float = Field(
        0.0,
        description="Credits deducted for this request (fetch fees + chunk fees + injection fees).",
    )
    credits_remaining: float = Field(
        0.0,
        description="Account credit balance after this request.",
    )

    def __repr__(self) -> str:
        return (
            f"AutoRagResult("
            f"pages_crawled={self.pages_crawled}, "
            f"total_chunks={self.total_chunks}, "
            f"vectors_upserted={self.vectors_upserted}, "
            f"root_url={self.root_url!r}, "
            f"credits_used={self.credits_used:.4f})"
        )


# ── Vector Query responses ────────────────────────────────────────────────────


class SuggestedModel(BaseModel):
    """An embedding model suggestion based on detected vector dimension."""

    provider: str = Field(..., description="Embedding provider key (e.g. 'openai').")
    model: str = Field(..., description="Model name (e.g. 'text-embedding-3-small').")
    label: str = Field(..., description="Human-readable label for display.")


class InspectVectorDBResult(BaseModel):
    """
    Result of :meth:`~scrapedatshi.pipeline.PipelineNamespace.inspect_vectordb`.

    Contains vector database metadata and embedding model suggestions based on
    the detected vector dimension. Use this before calling
    :meth:`~scrapedatshi.pipeline.PipelineNamespace.query_vectordb` to confirm
    which embedding model was used during ingestion.

    Free — no credits charged.
    """

    provider: str = Field(..., description="Vector DB provider key.")
    dimension: int = Field(
        0,
        description="Vector dimension detected from the index/collection. 0 if unknown.",
    )
    total_vector_count: int = Field(
        0, description="Total number of vectors in the index/collection."
    )
    namespace_vector_count: int | None = Field(
        None, description="Vector count in the specified namespace (Pinecone only)."
    )
    namespace: str | None = Field(
        None, description="Namespace queried (Pinecone only)."
    )
    suggested_models: list[SuggestedModel] = Field(
        default_factory=list,
        description=(
            "Embedding models that match the detected dimension. "
            "Confirm which model was used during ingestion before calling query_vectordb()."
        ),
    )
    dimension_known: bool = Field(
        False,
        description="True if the dimension was successfully read from the DB.",
    )
    note: str | None = Field(
        None, description="Guidance message about model selection."
    )

    def __repr__(self) -> str:
        return (
            f"InspectVectorDBResult("
            f"provider={self.provider!r}, "
            f"dimension={self.dimension}, "
            f"total_vector_count={self.total_vector_count}, "
            f"suggested_models={[m.label for m in self.suggested_models]})"
        )


class QueryResult(BaseModel):
    """A single result from a vector database similarity search."""

    text: str = Field(..., description="The chunk text content.")
    score: float = Field(
        ..., description="Similarity score (0–1, higher is more similar)."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata attached to this chunk (source URL, chunk_index, etc.).",
    )

    def __repr__(self) -> str:
        preview = self.text[:60].replace("\n", " ")
        return f"QueryResult(score={self.score:.3f}, text={preview!r}...)"


class RagChatResult(BaseModel):
    """
    Result of :meth:`~scrapedatshi.pipeline.PipelineNamespace.rag_chat`.

    Contains the LLM-generated answer grounded in retrieved chunks from your
    vector database, plus the source chunks used to generate the answer.

    Billing: $0.0002 per chunk retrieved (same as /v1/query).
    LLM tokens are your own cost — scrapedatshi does not bill for LLM usage.
    """

    query: str = Field(..., description="The original query string.")
    answer: str = Field(
        ...,
        description=(
            "The LLM-generated answer grounded in the retrieved chunks. "
            "If no chunks were found, contains a message explaining the issue."
        ),
    )
    embedding_provider: str = Field(..., description="Embedding provider used.")
    embedding_model: str = Field(..., description="Embedding model used.")
    vector_db_provider: str = Field(..., description="Vector DB provider queried.")
    llm_provider: str = Field(
        ..., description="LLM provider used for answer generation."
    )
    llm_model: str = Field(..., description="LLM model used for answer generation.")
    top_k_requested: int = Field(..., description="Number of chunks requested.")
    chunks_retrieved: int = Field(
        ..., description="Number of chunks actually retrieved and used as context."
    )
    sources: list[QueryResult] = Field(
        default_factory=list,
        description="Source chunks used to generate the answer, ordered by similarity score.",
    )
    credits_used: float = Field(
        0.0, description="Credits deducted ($0.0002 × chunks_retrieved)."
    )
    credits_remaining: float = Field(
        0.0, description="Account credit balance after this request."
    )
    llm_error: str | None = Field(
        None,
        description=(
            "If set, the LLM call failed but chunks were still retrieved. "
            "The answer field will contain an error description."
        ),
    )

    def __repr__(self) -> str:
        preview = self.answer[:60].replace("\n", " ")
        return (
            f"RagChatResult("
            f"query={self.query[:40]!r}, "
            f"chunks_retrieved={self.chunks_retrieved}, "
            f"credits_used={self.credits_used:.4f}, "
            f"answer={preview!r}...)"
        )


class QueryVectorDBResult(BaseModel):
    """
    Result of :meth:`~scrapedatshi.pipeline.PipelineNamespace.query_vectordb`.

    Contains the top-N most relevant chunks from your vector database,
    ordered by similarity score descending.

    Billing: $0.0002 per chunk returned.
    """

    query: str = Field(..., description="The original query string.")
    embedding_provider: str = Field(..., description="Embedding provider used.")
    embedding_model: str = Field(..., description="Embedding model used.")
    vector_db_provider: str = Field(..., description="Vector DB provider queried.")
    top_k_requested: int = Field(..., description="Number of results requested.")
    chunks_retrieved: int = Field(
        ..., description="Number of results actually returned."
    )
    results: list[QueryResult] = Field(
        default_factory=list,
        description="Matching chunks ordered by similarity score descending.",
    )
    credits_used: float = Field(
        0.0, description="Credits deducted ($0.0002 × chunks_retrieved)."
    )
    credits_remaining: float = Field(
        0.0, description="Account credit balance after this request."
    )

    def __repr__(self) -> str:
        return (
            f"QueryVectorDBResult("
            f"query={self.query[:40]!r}, "
            f"chunks_retrieved={self.chunks_retrieved}, "
            f"credits_used={self.credits_used:.4f})"
        )
