"""
scrapedatshi
~~~~~~~~~~~~
Official Python SDK for the scrapedatshi RAG pipeline API.

Quick start::

    from scrapedatshi import ScrapedatshiClient

    client = ScrapedatshiClient(api_key="sds_...")

    # Chunk a URL to JSON (no embedding required)
    result = client.pipeline.chunk_url("https://docs.example.com")
    for chunk in result.chunks:
        print(chunk.content)

    # Full pipeline — embed + inject to vector DB
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

    # Schema extraction — extract structured data using your LLM
    result = client.pipeline.extract(
        url="https://example.com/products/widget",
        schema={"title": "string — product name", "price": "number — price in USD"},
        llm_provider="openai",
        llm_api_key="sk-...",
    )
    print(result.extracted)

    # Multi-page schema extraction via crawl
    result = client.pipeline.extract_crawl(
        url="https://example.com/products",
        schema={"title": "string — product name", "price": "number — price in USD"},
        llm_provider="openai",
        llm_api_key="sk-...",
        max_pages=20,
    )
    for page in result.successful_results:
        print(page.url, page.extracted)

Full documentation: https://docs.scrapedatshi.com/sdk/python
Supported providers: from scrapedatshi.providers import EMBEDDING_PROVIDERS, VECTOR_DB_PROVIDERS, LLM_PROVIDERS
"""

from scrapedatshi.client import ScrapedatshiClient
from scrapedatshi.exceptions import (
    AuthError,
    InsufficientCreditsError,
    RateLimitError,
    ScrapedatshiError,
    ServerBusyError,
    ServerError,
    TierError,
    TimeoutError,
    ValidationError,
)
from scrapedatshi.models import (
    Chunk,
    ChunkResult,
    CrawlChunkResult,
    ExtractCrawlPageResult,
    ExtractCrawlResult,
    ExtractResult,
    IngestResult,
    SyncResult,
)

__version__ = "0.4.2"
__author__ = "scrapedatshi"
__all__ = [
    # Client
    "ScrapedatshiClient",
    # Exceptions
    "ScrapedatshiError",
    "AuthError",
    "InsufficientCreditsError",
    "RateLimitError",
    "TierError",
    "ValidationError",
    "ServerError",
    "ServerBusyError",
    "TimeoutError",
    # Models
    "Chunk",
    "ChunkResult",
    "CrawlChunkResult",
    "SyncResult",
    "IngestResult",
    "ExtractResult",
    "ExtractCrawlResult",
    "ExtractCrawlPageResult",
]
