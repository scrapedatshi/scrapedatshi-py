"""
scrapedatshi.pipeline._namespace
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
PipelineNamespace — the main entry point for all pipeline operations.

Accessed via ``client.pipeline.*``

This class composes all pipeline methods via mixins:
    ChunkMixin   — chunk_url, chunk_file, crawl
    IngestMixin  — ingest, ingest_folder
    SyncMixin    — sync, autorag
    ExtractMixin — extract, extract_crawl
    QueryMixin   — inspect_vectordb, query_vectordb, rag_chat
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi.pipeline._chunk import ChunkMixin
from scrapedatshi.pipeline._extract import ExtractMixin
from scrapedatshi.pipeline._ingest import IngestMixin
from scrapedatshi.pipeline._query import QueryMixin
from scrapedatshi.pipeline._sync import SyncMixin


class PipelineNamespace(ChunkMixin, IngestMixin, SyncMixin, ExtractMixin, QueryMixin):
    """
    All pipeline operations, accessible via ``client.pipeline``.

    Chunk-to-JSON (no embedding required):
        - chunk_url()        / chunk_url_async()
        - chunk_file()       / chunk_file_async()
        - crawl()            / crawl_async()

    Full Pipeline (embed + vector DB inject):
        - sync()             / sync_async()
        - ingest()           / ingest_async()
        - ingest_folder()    / ingest_folder_async()
        - autorag()          / autorag_async()

    Schema Extraction:
        - extract()          / extract_async()
        - extract_crawl()    / extract_crawl_async()

    Vector DB Query:
        - inspect_vectordb() / inspect_vectordb_async()
        - query_vectordb()   / query_vectordb_async()
        - rag_chat()         / rag_chat_async()

    All methods return typed response models with ``credits_used`` and
    ``credits_remaining`` fields for programmatic spend tracking.
    """

    def __init__(self, client: "ScrapedatshiClient") -> None:
        self._client = client
