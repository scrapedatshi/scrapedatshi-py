# scrapedatshi-py

Official Python SDK for the [scrapedatshi](https://scrapedatshi.com) RAG pipeline API.

Scrape URLs, chunk documents, embed content, inject into vector databases, and extract structured data — all from a clean, typed Python interface.

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

# Chunk a URL to JSON (no embedding required)
result = client.pipeline.chunk_url("https://docs.example.com")

print(f"Got {result.total_chunks} chunks")
print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")
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
New accounts receive **$1.00 free credits** — no credit card required.

---

## Pricing

scrapedatshi uses a **pay-per-use credit wallet** — no subscriptions, no monthly fees.
Credits are deducted after each successful API call. Failed requests are never charged.

| Operation | Rate | Applies To |
|---|---|---|
| URL Fetch | $0.0020 / URL | /v1/rag-chunk, /v1/crawl-chunk, /v1/sync, /v1/ingest |
| Spider Fetch | $0.0050 / URL | /v1/spider (replaces standard URL fetch) |
| Chunk Fee | $0.0005 / chunk | All routes (per individual chunk generated) |
| Injection Fee | $0.0030 / chunk | /v1/sync, /v1/ingest (vector DB upserts) |
| Contextual Retrieval | $0.0030 / URL | When `contextual_retrieval=True` is enabled |
| JS Render | $0.0050 / URL | When `js_render=True` (Playwright processing) |
| Schema Extract | $0.0030 + ($0.0001 × field) | /v1/extract baseline processing |

Top up your balance at [scrapedatshi.com/portal/billing](https://scrapedatshi.com/portal/billing).

---

## Pipeline Methods

### Chunk to JSON

No embedding or vector DB required. Returns structured JSON chunks from any source.

#### Chunk a URL

```python
result = client.pipeline.chunk_url("https://docs.example.com")

# result.chunks              → list[Chunk]
# result.total_chunks        → int
# result.source              → str (the URL)
# result.credits_used        → float
# result.credits_remaining   → float
# result.content_truncated   → bool (True if content exceeded ~75,000 words)
```

#### Chunk a URL with JS rendering

For JavaScript-heavy pages and SPAs that require a browser to render:

```python
result = client.pipeline.chunk_url(
    "https://spa.example.com/dashboard",
    js_render=True,
)
```

#### Chunk a local file

Supports PDF, MD, TXT, YAML, YML, and JSON.

```python
result = client.pipeline.chunk_file("./docs/manual.pdf")

print(f"Got {result.total_chunks} chunks from {result.source}")
print(f"Cost: ${result.credits_used:.4f}")
```

#### Crawl a website

Crawls via sitemap or spider and chunks all pages.

```python
# Sitemap crawl (default) — reads sitemap.xml
result = client.pipeline.crawl("https://example.com", max_pages=10)

# Spider crawl — follows links, works on any site
result = client.pipeline.crawl(
    "https://example.com",
    crawl_mode="spider",
    max_pages=5,
    include_pattern="/docs/",
    exclude_pattern="/blog/",
)

print(f"Crawled {result.pages_crawled} pages → {result.total_chunks} chunks")
print(f"Cost: ${result.credits_used:.4f}")
```

---

### Full Pipeline — Embed + Inject

Scrape, embed, and inject directly into your vector database in one call.

#### Sync a URL

```python
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

print(f"Upserted {result.vectors_upserted} vectors ({result.total_tokens} tokens)")
print(f"Cost: ${result.credits_used:.4f}")
```

#### Ingest a local file

```python
result = client.pipeline.ingest(
    file_path="./docs/manual.pdf",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    vector_db="qdrant",
    vector_db_config={
        "url": "https://your-cluster.qdrant.io",
        "collection_name": "documents",
        "api_key": "qdrant-key",  # optional for local Qdrant
    },
)
```

---

### Schema Extraction

Extract structured data from any URL using your own LLM key. Define a schema and the API returns a typed JSON object — or a list of objects for pages with multiple items.

#### Extract a single object

```python
result = client.pipeline.extract(
    url="https://example.com/products/widget-pro",
    schema={
        "title": "string — the product name",
        "price": "number — the price in USD",
        "in_stock": "boolean — whether the item is in stock",
        "description": "string — the product description",
    },
    llm_provider="openai",
    llm_api_key="sk-...",
)

print(result.extracted)
# → {"title": "Widget Pro", "price": 29.99, "in_stock": True, "description": "..."}
print(f"Cost: ${result.credits_used:.4f}")
```

#### Extract a list of items

Use `extract_as_list=True` for pages with multiple matching items (product listings, article feeds, search results):

```python
result = client.pipeline.extract(
    url="https://example.com/products",
    schema={
        "title": "string — the product name",
        "price": "number — the price in USD",
    },
    llm_provider="openai",
    llm_api_key="sk-...",
    extract_as_list=True,
)

print(f"Extracted {result.item_count} products")
for product in result.extracted:
    print(f"  {product['title']}: ${product['price']}")
```

#### Extract from a JS-rendered page

```python
result = client.pipeline.extract(
    url="https://spa.example.com/data",
    schema={"value": "string — the data value"},
    llm_provider="anthropic",
    llm_api_key="sk-ant-...",
    js_render=True,
)
```

---

### Contextual Retrieval (RAG 2.0)

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

Available on all pipeline methods: `chunk_url()`, `chunk_file()`, `crawl()`, `sync()`, `ingest()`.

---

## Supported Providers

Discover all supported providers programmatically:

```python
from scrapedatshi.providers import (
    EMBEDDING_PROVIDERS,
    VECTOR_DB_PROVIDERS,
    LLM_PROVIDERS,
)

# List all embedding providers
for key, info in EMBEDDING_PROVIDERS.items():
    print(f"{key}: {info['label']} — default model: {info['default_model']}")
    print(f"  {info['notes']}")
# → openai: OpenAI — default model: text-embedding-3-small

# Check required fields for a vector DB
print(VECTOR_DB_PROVIDERS["pinecone"]["required_fields"])
# → ["api_key", "index_host"]
```

### Embedding Providers

| Key | Provider | Default Model | Notes |
|---|---|---|---|
| `openai` | OpenAI | `text-embedding-3-small` | 1536 dims. Also: `text-embedding-3-large` (3072), `text-embedding-ada-002` (1536) |
| `cohere` | Cohere | `embed-english-v3.0` | 1024 dims. Also: `embed-multilingual-v3.0`, `embed-english-light-v3.0` (384) |
| `gemini` | Google Gemini | `gemini-embedding-001` | 3072 dims. Also: `text-embedding-004` (768) |
| `mistral` | Mistral | `mistral-embed` | 1024 dims |
| `voyage` | Voyage AI | `voyage-3` | 1024 dims. Also: `voyage-3-lite` (512), `voyage-code-3`, `voyage-finance-2`, `voyage-law-2` |

Models are discovered dynamically after key verification — you always get the latest available models for your account.

### Vector Database Providers

| Key | Provider | Required Fields |
|---|---|---|
| `pinecone` | Pinecone | `api_key`, `index_host` |
| `qdrant` | Qdrant | `url`, `collection_name` |
| `supabase` | Supabase (pgvector) | `connection_string`, `table_name` |
| `weaviate` | Weaviate | `url`, `class_name` |
| `mongodb` | MongoDB Atlas | `connection_string`, `database_name`, `collection_name` |
| `azure_cosmos` | Azure Cosmos DB (NoSQL) | `connection_string`, `database_name`, `container_name` |
| `azure_cosmos_mongo` | Azure Cosmos DB (MongoDB API) | `connection_string`, `database_name`, `collection_name` |

### LLM Providers (for Contextual Retrieval & Schema Extraction)

| Key | Provider | Default Model | Context Window |
|---|---|---|---|
| `openai` | OpenAI | `gpt-4o-mini` | Standard (mini, etc.): 8k chars · Advanced (gpt-4o, etc.): 30k chars |
| `anthropic` | Anthropic | `claude-3-haiku-20240307` | Standard (haiku): 8k chars · Advanced (sonnet, opus): 30k chars |
| `gemini` | Google Gemini | `gemini-1.5-flash` | Standard (flash, lite, nano): 8k chars · Advanced (pro, etc.): 30k chars |

**Model tiers:** The API automatically selects the context window based on the model name. Standard models (containing "mini", "flash", "haiku", "lite", or "nano") use an 8,000 character context window. All other models are treated as Advanced and use a 30,000 character context window. Use an advanced model for long-form pages (documentation, legal docs, research papers).

---

## Async Support

All methods have an `_async` variant for use with `asyncio`.

```python
import asyncio
from scrapedatshi import ScrapedatshiClient

async def main():
    async with ScrapedatshiClient(api_key="sds_...") as client:
        result = await client.pipeline.chunk_url_async("https://docs.example.com")
        print(f"Got {result.total_chunks} chunks — cost ${result.credits_used:.4f}")

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
        total_cost = sum(r.credits_used for r in results)
        print(f"Processed {len(urls)} URLs → {total} total chunks — total cost ${total_cost:.4f}")
```

---

## Response Models

All methods return typed Pydantic models with full IDE autocomplete support.
Every response includes `credits_used` and `credits_remaining` for programmatic spend tracking.

### `ChunkResult`

```python
result.chunks                  # list[Chunk]
result.total_chunks            # int
result.source                  # str
result.contextual_retrieval_used  # bool
result.content_truncated       # bool — True if content exceeded ~75,000 words
result.credits_used            # float — credits deducted for this request
result.credits_remaining       # float — account balance after this request
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
result.credits_used        # float
result.credits_remaining   # float
```

### `SyncResult` / `IngestResult`

```python
result.status              # "success" | "partial" | "error"
result.chunks_created      # int
result.vectors_upserted    # int
result.total_tokens        # int
result.embedding_provider  # str
result.vector_db_provider  # str
result.credits_used        # float
result.credits_remaining   # float
```

### `ExtractResult`

```python
result.extracted           # dict | list[dict] — the extracted data
result.field_count         # int — number of schema fields
result.item_count          # int | None — number of items (list mode only)
result.is_list             # bool — True if extracted is a list
result.url                 # str — the URL that was scraped
result.llm_provider        # str
result.llm_model           # str
result.schema_fields       # list[str] — field names from your schema
result.js_render           # bool — whether JS rendering was used
result.content_warning     # str | None — warning if content may be incomplete
result.credits_used        # float
result.credits_remaining   # float
```

---

### Schema Extraction via Crawl

Crawl an entire domain and extract structured data from every page in a single call. Each page is processed independently — failed pages return an error object without aborting the batch. **Only successfully extracted pages are billed.**

```python
result = client.pipeline.extract_crawl(
    url="https://example.com/products",
    schema={
        "title": "string — the product name",
        "price": "number — the price in USD",
        "in_stock": "boolean — whether the item is in stock",
    },
    llm_provider="openai",
    llm_api_key="sk-...",
    max_pages=20,
    include_pattern="/products/",
)

print(f"Extracted {result.pages_extracted}/{result.pages_attempted} pages")
print(f"Cost: ${result.credits_used:.4f} | Remaining: ${result.credits_remaining:.4f}")

# Iterate all results
for page in result.results:
    if page.ok:
        print(f"  {page.url}: {page.extracted}")
    else:
        print(f"  {page.url}: FAILED — {page.error}")

# Access only successful results
for page in result.successful_results:
    print(page.extracted["title"], page.extracted["price"])
```

**Billing:** `$0.0020 + $0.0030 + (N_fields × $0.0001)` per successfully extracted page.
Example: 20 pages × 3 fields = 20 × $0.0053 = **$0.106**

#### Spider crawl mode

```python
result = client.pipeline.extract_crawl(
    url="https://example.com",
    schema={"title": "string — the page title", "summary": "string — a brief summary"},
    llm_provider="anthropic",
    llm_api_key="sk-ant-...",
    crawl_mode="spider",
    max_pages=10,
)
```

#### `ExtractCrawlResult` model

```python
result.results             # list[ExtractCrawlPageResult] — per-page results
result.pages_extracted     # int — successfully extracted
result.pages_failed        # int — failed (not billed)
result.pages_attempted     # int — total attempted
result.pages_discovered    # int — total URLs found in sitemap/spider
result.successful_results  # list[ExtractCrawlPageResult] — only ok pages
result.failed_results      # list[ExtractCrawlPageResult] — only failed pages
result.job_id              # str | None — persistent job ID
result.credits_used        # float
result.credits_remaining   # float
```

Each `ExtractCrawlPageResult`:

```python
page.url        # str — the URL scraped
page.status     # "ok" | "error"
page.extracted  # dict | list[dict] | None — extracted data (None on error)
page.error      # str | None — error message (None on success)
page.ok         # bool — True if status == "ok"
```

---

## Error Handling

```python
from scrapedatshi.exceptions import (
    AuthError,              # Invalid or missing API key (401/403)
    InsufficientCreditsError,  # Balance too low — top up at portal/billing (402)
    RateLimitError,         # Per-request hard cap or rate limit exceeded (429)
    ValidationError,        # Bad request payload (422)
    ServerBusyError,        # Server at capacity — retry after e.retry_after seconds (503)
    ServerError,            # API server error (5xx)
    TimeoutError,           # Request timed out
    ScrapedatshiError       # Base exception — catch-all
)

try:
    result = client.pipeline.sync(
        url="https://docs.example.com",
        embedding_provider="openai",
        embedding_api_key="sk-...",
        vector_db="pinecone",
        vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
    )
except InsufficientCreditsError:
    print("Balance too low — top up at scrapedatshi.com/portal/billing")
except RateLimitError as e:
    print(f"Rate limit hit: {e.message}")
except ScrapedatshiError as e:
    print(f"API error {e.status_code}: {e.message}")
```

#### Handling `ServerBusyError` (503)

Large crawl jobs use a server-side queue. When the queue is full, the API returns HTTP 503 with a `Retry-After` header. The SDK surfaces this as `ServerBusyError` with a `retry_after` attribute:

```python
import time
from scrapedatshi.exceptions import ServerBusyError

try:
    result = client.pipeline.extract_crawl(
        url="https://example.com",
        schema={"title": "string — the page title"},
        llm_provider="openai",
        llm_api_key="sk-...",
        max_pages=50,
    )
except ServerBusyError as e:
    wait = e.retry_after or 30  # seconds to wait (from Retry-After header)
    print(f"Server busy — retrying in {wait}s")
    time.sleep(wait)
    # retry the request...
```

---

## Hard Caps

Per-request hard caps protect server stability and apply to all accounts:

| Cap | Limit |
|---|---|
| Max pages / sitemap crawl | 200 |
| Max pages / spider crawl | 50 |
| Max chunks / request | 10,000 |
| Max content size | ~75,000 words (auto-truncated) |

**Sitemap crawl** (`crawl_mode="sitemap"`): Reads `sitemap.xml` to discover URLs. Up to 200 pages per request.

**Spider crawl** (`crawl_mode="spider"`): Follows `<a href>` links via BFS. Up to 50 pages per request. More compute-intensive — start small and increase as needed.

Exceeding a hard cap returns HTTP 400. Content exceeding the size limit is automatically
truncated — check `result.content_truncated` to detect this.

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
