"""
scrapedatshi.pipeline
~~~~~~~~~~~~~~~~~~~~~
Pipeline namespace — re-exports PipelineNamespace for backward compatibility.

All pipeline methods are accessible via ``client.pipeline.*``.
The implementation is split across focused submodules:

    _chunk.py        — chunk_url, chunk_file, crawl
    _ingest.py       — ingest, ingest_folder
    _sync.py         — sync, autorag
    _extract.py      — extract, extract_crawl
    _query.py        — inspect_vectordb, query_vectordb, rag_chat
    _crawl_helpers.py — local crawl engine (sitemap + spider BFS)
    _ingest_helpers.py — folder ingestion engine + file text extraction

Importing ``from scrapedatshi.pipeline import PipelineNamespace`` continues
to work exactly as before — no breaking changes.
"""

from scrapedatshi.pipeline._namespace import PipelineNamespace

__all__ = ["PipelineNamespace"]
