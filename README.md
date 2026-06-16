# scrapedatshi-py

Official Python SDK for the [scrapedatshi](https://scrapedatshi.com) RAG pipeline API.

Scrape URLs, chunk documents, embed content, and inject into vector databases — all from a clean, typed Python interface.

---

## Installation

```bash
pip install scrapedatshi
```

Requires Python 3.10+.

---

## Quick Start

```python
from scrapedatshi import ScrapedatshiClient

client = ScrapedatshiClient(api_key="sds_...")

# Chunk a URL to JSON (all tiers — no embedding required)
result = client.pipeline.chunk_url("https://docs.example.com")

print(f"Got {result.total_chunks} chunks")
for chunk in result.chunks:
    print(chunk.content[:80])
```

---

## Authentication

Pass your API key directly or set the `SCRAPEDATSHI_API_KEY` environment variable:

```bash
export SCRAPEDATSHI_API_KEY="sds_..."
```

```python
# Explicit key
client = ScrapedatshiClient(api_key="sds_...")

# From environment variable
client = ScrapedatshiClient()
```

Get your API key at [scrapedatshi.com/portal/register](https://scrapedatshi.com/portal/register).

---

## Pipeline Methods

### Chunk to JSON (all tiers)

No embedding or vector DB required. Returns structured JSON chunks from any source.

#### Chunk a URL

```python
result = client.pipeline.chunk_url("https://docs.example.com")

# result.chunks       → list[Chunk]
# result.total_chunks → int
# result.source       → str (the URL)
```

#### Chunk a local file

Supports PDF, DOCX, TXT, MD, and HTML.

```python
result = client.pipeline.chunk_file("./docs/manual.pdf")

print(f"Got {result.total_chunks} chunks from {result.source}")
```

#### Crawl a website (Basic tier+)

Crawls via sitemap and chunks all pages.

```python
result = client.pipeline.crawl("https://example.com", max_pages=10)

print(f"Crawled {result.pages_crawled} pages → {result.total_chunks} chunks")
```

---

### Full Pipeline — Embed + Inject (Pro/Enterprise)

Scrape, embed, and inject directly into your vector database in one call.

#### Sync a URL

```python
result = client.pipeline.sync(
    url="https://docs.example.com",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    vector_db="pinecone",
    vector_db_api_key="pc-...",
    index_name="my-docs",
)

print(f"Upserted {result.vectors_upserted} vectors ({result.total_tokens} tokens)")
```

#### Ingest a local file

```python
result = client.pipeline.ingest(
    file_path="./docs/manual.pdf",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    vector_db="pinecone",
    vector_db_api_key="pc-...",
    index_name="my-docs",
)
```

---

### Contextual Retrieval (RAG 2.0) — Basic tier+

Prepend an LLM-generated document summary to every chunk before embedding, dramatically improving retrieval accuracy.

```python
result = client.pipeline.chunk_url(
    "https://docs.example.com",
    contextual_retrieval=True,
    llm_provider="openai",
    llm_api_key="sk-...",
    llm_model="gpt-4o-mini",
)
```

Supported LLM providers: `openai`, `anthropic`, `gemini`

---

## Async Support

All methods have an `_async` variant for use with `asyncio`.

```python
import asyncio
from scrapedatshi import ScrapedatshiClient

async def main():
    async with ScrapedatshiClient(api_key="sds_...") as client:
        result = await client.pipeline.chunk_url_async("https://docs.example.com")
        print(f"Got {result.total_chunks} chunks")

asyncio.run(main())
```

#### Parallel processing with `asyncio.gather`

```python
async def main():
    async with ScrapedatshiClient(api_key="sds_...") as client:
        urls = [
            "https://docs.example.com/page1",
            "https://docs.example.com/page2",
            "https://docs.example.com/page3",
        ]
        results = await asyncio.gather(
            *[client.pipeline.chunk_url_async(url) for url in urls]
        )
        total = sum(r.total_chunks for r in results)
        print(f"Processed {len(urls)} URLs → {total} total chunks")
```

---

## Response Models

All methods return typed Pydantic models with full IDE autocomplete support.

### `ChunkResult`

```python
result.chunks              # list[Chunk]
result.total_chunks        # int
result.source              # str
result.contextual_retrieval_used  # bool
```

### `Chunk`

```python
chunk.content              # str — the chunk text
chunk.token_estimate       # int — estimated token count
chunk.metadata             # dict — source URL, page number, etc.
```

### `CrawlChunkResult`

```python
result.chunks              # list[Chunk]
result.total_chunks        # int
result.pages_crawled       # int
result.source_url          # str
```

### `SyncResult` / `IngestResult`

```python
result.status              # "success" | "error"
result.chunks_created      # int
result.vectors_upserted    # int
result.total_tokens        # int
result.embedding_provider  # str
result.vector_db_provider  # str
```

---

## Error Handling

```python
from scrapedatshi.exceptions import (
    AuthError,        # Invalid or missing API key (401/403)
    TierError,        # Feature not available on your plan (403)
    RateLimitError,   # Monthly or per-minute limit exceeded (429)
    ValidationError,  # Bad request payload (422)
    ServerError,      # API server error (5xx)
    TimeoutError,     # Request timed out
    ScrapedatshiError # Base exception — catch-all
)

try:
    result = client.pipeline.sync(
        url="https://docs.example.com",
        embedding_provider="openai",
        embedding_api_key="sk-...",
        vector_db="pinecone",
        vector_db_api_key="pc-...",
        index_name="my-docs",
    )
except TierError as e:
    print(f"Upgrade required: {e.message}")
except RateLimitError as e:
    print(f"Rate limit hit: {e.message}")
except ScrapedatshiError as e:
    print(f"API error {e.status_code}: {e.message}")
```

---

## Tier Limits

| Feature | Free | Basic | Pro | Enterprise |
|---|---|---|---|---|
| Price | $0/mo | $9/mo | $29/mo | $49/mo + usage |
| Chunk to JSON | ✓ | ✓ | ✓ | ✓ |
| Sitemap Crawl | — | ✓ | ✓ | ✓ |
| Contextual Retrieval | — | ✓ | ✓ | ✓ |
| Full Pipeline | — | — | ✓ | ✓ |
| Deep Spider Crawl | — | — | ✓ | ✓ |
| Max pages / crawl | 5 | 10 | 25 | 50 |
| Max chunks / request | 500 | 2,000 | 10,000 | Unlimited |
| Concurrent requests | 1 | 3 | 10 | 25 |

---

## Development

```bash
git clone https://github.com/mxchris18/scrapedatshi-py
cd scrapedatshi-py
pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](https://github.com/mxchris18/scrapedatshi-py/blob/main/LICENSE).
