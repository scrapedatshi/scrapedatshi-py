"""
scrapedatshi
~~~~~~~~~~~~
Official Python SDK for the scrapedatshi RAG pipeline API.

Quick start::

    from scrapedatshi import ScrapedatshiClient

    client = ScrapedatshiClient(api_key="sds_...")

    # Chunk a URL to JSON (all tiers)
    result = client.pipeline.chunk_url("https://docs.example.com")
    for chunk in result.chunks:
        print(chunk.content)

    # Full pipeline — embed + inject to vector DB (Pro/Enterprise)
    result = client.pipeline.sync(
        url="https://docs.example.com",
        embedding_provider="openai",
        embedding_api_key="sk-...",
        vector_db="pinecone",
        vector_db_api_key="pc-...",
        index_name="my-docs",
    )

Full documentation: https://docs.scrapedatshi.com/sdk/python
"""

from scrapedatshi.client import ScrapedatshiClient
from scrapedatshi.exceptions import (
    AuthError,
    RateLimitError,
    ScrapedatshiError,
    ServerError,
    TierError,
    TimeoutError,
    ValidationError,
)
from scrapedatshi.models import (
    Chunk,
    ChunkResult,
    CrawlChunkResult,
    IngestResult,
    SyncResult,
)

__version__ = "0.1.0"
__author__ = "scrapedatshi"
__all__ = [
    # Client
    "ScrapedatshiClient",
    # Exceptions
    "ScrapedatshiError",
    "AuthError",
    "RateLimitError",
    "TierError",
    "ValidationError",
    "ServerError",
    "TimeoutError",
    # Models
    "Chunk",
    "ChunkResult",
    "CrawlChunkResult",
    "SyncResult",
    "IngestResult",
]
