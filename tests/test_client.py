"""
tests/test_client.py
~~~~~~~~~~~~~~~~~~~~
Unit tests for the scrapedatshi SDK using respx to mock httpx transport.

Run with:
    pip install -e ".[dev]"
    pytest
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from scrapedatshi import ScrapedatshiClient
from scrapedatshi.exceptions import AuthError, RateLimitError, TierError
from scrapedatshi.models import ChunkResult, CrawlChunkResult, IngestResult, SyncResult

# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_API_KEY = "sds_test_key_1234567890"
BASE_URL = "https://api.scrapedatshi.com"

SAMPLE_CHUNKS = [
    {"text": "Hello world chunk one.", "token_estimate": 5, "metadata": {}},
    {"text": "Hello world chunk two.", "token_estimate": 5, "metadata": {}},
]

CHUNK_RESPONSE = {
    "chunks": SAMPLE_CHUNKS,
    "total_chunks": 2,
    "contextual_retrieval_used": False,
}

SYNC_RESPONSE = {
    "status": "success",
    "chunks_created": 10,
    "vectors_upserted": 10,
    "total_tokens": 1500,
    "contextual_retrieval_used": False,
}


@pytest.fixture
def client() -> ScrapedatshiClient:
    return ScrapedatshiClient(api_key=FAKE_API_KEY, base_url=BASE_URL)


# ── Auth tests ────────────────────────────────────────────────────────────────


def test_raises_auth_error_without_api_key(monkeypatch):
    """Client should raise AuthError if no key is provided and env var is unset."""
    monkeypatch.delenv("SCRAPEDATSHI_API_KEY", raising=False)
    with pytest.raises(AuthError):
        ScrapedatshiClient()


def test_reads_api_key_from_env(monkeypatch):
    """Client should read the API key from SCRAPEDATSHI_API_KEY env var."""
    monkeypatch.setenv("SCRAPEDATSHI_API_KEY", FAKE_API_KEY)
    c = ScrapedatshiClient()
    assert c._api_key == FAKE_API_KEY


def test_repr_masks_api_key():
    """Client repr should mask the API key."""
    c = ScrapedatshiClient(api_key=FAKE_API_KEY)
    assert FAKE_API_KEY not in repr(c)
    assert "sds_test" in repr(c)


# ── chunk_url tests ───────────────────────────────────────────────────────────


@respx.mock
def test_chunk_url_returns_chunk_result(client):
    """chunk_url() should return a ChunkResult with correct data."""
    respx.post(f"{BASE_URL}/v1/rag-chunk").mock(
        return_value=httpx.Response(200, json=CHUNK_RESPONSE)
    )

    result = client.pipeline.chunk_url("https://docs.example.com")

    assert isinstance(result, ChunkResult)
    assert result.total_chunks == 2
    assert result.source == "https://docs.example.com"
    assert len(result.chunks) == 2
    assert result.chunks[0].content == "Hello world chunk one."
    assert result.contextual_retrieval_used is False


@respx.mock
def test_chunk_url_sends_api_key_header(client):
    """chunk_url() should include the X-API-Key header."""
    route = respx.post(f"{BASE_URL}/v1/rag-chunk").mock(
        return_value=httpx.Response(200, json=CHUNK_RESPONSE)
    )

    client.pipeline.chunk_url("https://docs.example.com")

    assert route.called
    request = route.calls[0].request
    assert request.headers["X-API-Key"] == FAKE_API_KEY


@respx.mock
def test_chunk_url_raises_rate_limit_error(client):
    """chunk_url() should raise RateLimitError on HTTP 429."""
    respx.post(f"{BASE_URL}/v1/rag-chunk").mock(
        return_value=httpx.Response(
            429, json={"detail": "Monthly limit reached for your Free plan."}
        )
    )

    with pytest.raises(RateLimitError) as exc_info:
        client.pipeline.chunk_url("https://docs.example.com")

    assert exc_info.value.status_code == 429


@respx.mock
def test_chunk_url_raises_tier_error(client):
    """chunk_url() should raise AuthError on HTTP 403 (tier gate removed; server now returns AuthError)."""
    respx.post(f"{BASE_URL}/v1/rag-chunk").mock(
        return_value=httpx.Response(
            403, json={"detail": "Upgrade your plan to access this feature."}
        )
    )

    with pytest.raises(AuthError):
        client.pipeline.chunk_url("https://docs.example.com")


# ── crawl tests ───────────────────────────────────────────────────────────────


@respx.mock
def test_crawl_returns_crawl_chunk_result(client):
    """crawl() should return a CrawlChunkResult."""
    crawl_response = {
        **CHUNK_RESPONSE,
        "pages_crawled": 5,
    }
    respx.post(f"{BASE_URL}/v1/crawl-chunk").mock(
        return_value=httpx.Response(200, json=crawl_response)
    )

    result = client.pipeline.crawl("https://example.com", max_pages=5)

    assert isinstance(result, CrawlChunkResult)
    assert result.pages_crawled == 5
    assert result.source_url == "https://example.com"
    assert result.total_chunks == 2


# ── sync tests ────────────────────────────────────────────────────────────────


@respx.mock
def test_sync_returns_sync_result(client):
    """sync() should return a SyncResult with correct data."""
    respx.post(f"{BASE_URL}/v1/sync").mock(
        return_value=httpx.Response(200, json=SYNC_RESPONSE)
    )

    result = client.pipeline.sync(
        url="https://docs.example.com",
        embedding_provider="openai",
        embedding_api_key="sk-test",
        vector_db="pinecone",
        vector_db_config={"api_key": "pc-test", "index_host": "https://my-index.svc.pinecone.io"},
    )

    assert isinstance(result, SyncResult)
    assert result.status == "success"
    assert result.chunks_created == 10
    assert result.vectors_upserted == 10
    assert result.embedding_provider == "openai"
    assert result.vector_db_provider == "pinecone"


@respx.mock
def test_sync_sends_correct_payload(client):
    """sync() should send all required fields in the JSON payload."""
    route = respx.post(f"{BASE_URL}/v1/sync").mock(
        return_value=httpx.Response(200, json=SYNC_RESPONSE)
    )

    client.pipeline.sync(
        url="https://docs.example.com",
        embedding_provider="openai",
        embedding_api_key="sk-test",
        vector_db="pinecone",
        vector_db_config={"api_key": "pc-test", "index_host": "https://my-index.svc.pinecone.io"},
    )

    request = route.calls[0].request
    body = json.loads(request.content)
    assert body["url"] == "https://docs.example.com"
    assert body["embedding"]["provider"] == "openai"
    assert body["vector_db"]["provider"] == "pinecone"
    assert body["vector_db"]["api_key"] == "pc-test"


# ── Async tests ───────────────────────────────────────────────────────────────


@respx.mock
@pytest.mark.asyncio
async def test_chunk_url_async_returns_chunk_result(client):
    """chunk_url_async() should return a ChunkResult."""
    respx.post(f"{BASE_URL}/v1/rag-chunk").mock(
        return_value=httpx.Response(200, json=CHUNK_RESPONSE)
    )

    result = await client.pipeline.chunk_url_async("https://docs.example.com")

    assert isinstance(result, ChunkResult)
    assert result.total_chunks == 2


@respx.mock
@pytest.mark.asyncio
async def test_async_context_manager():
    """Client should work as an async context manager."""
    respx.post(f"{BASE_URL}/v1/rag-chunk").mock(
        return_value=httpx.Response(200, json=CHUNK_RESPONSE)
    )

    async with ScrapedatshiClient(api_key=FAKE_API_KEY, base_url=BASE_URL) as c:
        result = await c.pipeline.chunk_url_async("https://docs.example.com")

    assert isinstance(result, ChunkResult)


# ── Model tests ───────────────────────────────────────────────────────────────


def test_chunk_result_len():
    """ChunkResult.__len__ should return total_chunks."""
    result = ChunkResult(
        chunks=SAMPLE_CHUNKS,
        total_chunks=2,
        source="https://example.com",
    )
    assert len(result) == 2


def test_chunk_repr():
    """Chunk.__repr__ should show token count and content preview."""
    from scrapedatshi.models import Chunk

    chunk = Chunk(
        text="Hello world this is a test chunk.", token_estimate=8, metadata={}
    )
    r = repr(chunk)
    assert "tokens=8" in r
    assert "Hello world" in r
