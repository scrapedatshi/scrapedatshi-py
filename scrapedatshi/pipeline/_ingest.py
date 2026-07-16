"""
scrapedatshi.pipeline._ingest
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ingest methods: ingest (single file) and ingest_scraped (bulk scraper output).

Requires embedding provider + vector DB keys.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi.models import IngestScrapedResult, IngestResult
from scrapedatshi.pipeline._ingest_helpers import (
    _INGEST_FOLDER_EXTENSIONS,
    _JSON_TEXT_KEYS,
    _ingest_folder_locally,
    _ingest_folder_locally_async,
)


class IngestMixin:
    """Mixin providing ingest and ingest_scraped methods."""

    _client: "ScrapedatshiClient"

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

        Supports: .pdf, .md, .txt, .yaml, .yml, .json, .csv, .xlsx, .docx, .ipynb,
        and all common code file types.
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

    # ── Full Pipeline — Scraped Output Ingest ────────────────────────────────

    def ingest_scraped(
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
    ) -> IngestScrapedResult:
        """
        Bulk ingest a folder of pre-scraped files — chunk, embed, and inject into a vector DB.

        Designed for output from web scrapers (Scrapy, Playwright, Apify, custom scripts).
        Each file is parsed locally, chunked, embedded, and injected individually.

        Supported file types: .md, .txt, .json, .yaml, .yml, .csv, .xlsx, .xls,
        .docx, .ipynb, .html, .htm, .xml, .toml, .ini, .cfg, and all common code
        file types (.py, .js, .ts, .sql, .go, .rb, .java, .cs, .cpp, .c, .rs, etc.)

        Special handling:
        - JSON arrays are automatically detected and each item is extracted and
          ingested individually (Scrapy/crawler output format).
        - .py files are split by top-level class/function (AST-aware).
        - .sql files are split by statement block (CREATE TABLE, SELECT, etc.).
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

    async def ingest_scraped_async(
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
    ) -> IngestScrapedResult:
        """Async version of :meth:`ingest_scraped`."""
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
