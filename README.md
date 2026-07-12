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

result = client.pipeline.chunk_url("https://docs.example.com")
print(f"Got {result.total_chunks} chunks — cost ${result.credits_used:.4f}")
for chunk in result.chunks:
    print(chunk.content[:80])
```

---

## CLI — Project Scaffolding

The SDK ships with a `scrapedatshi` CLI command that generates a ready-to-run sandbox project with pre-configured example scripts for every pipeline method.

```bash
scrapedatshi init my-project
```

This creates:

```
my-project/
├── .env                        ← add your API keys here (gitignored)
├── .gitignore
├── README.md
└── examples/
    ├── 00_discover_providers.py   ← list all providers + required fields (no keys needed)
    ├── 01_chunk_url.py
    ├── 02_chunk_file.py
    ├── 03_crawl_site.py
    ├── 04_sync_to_vdb.py
    ├── 05_ingest_file.py
    ├── 06_ingest_folder.py
    ├── 07_autorag.py
    ├── 08_schema_extract.py
    ├── 09_extract_crawl.py
    ├── 10_query_vdb.py
    ├── 11_rag_chat.py
    └── 12_inspect_vdb.py
```

Each script has a clearly marked `# ── CONFIGURE ──` block at the top — just fill in your target URL, file path, or keys and run it. Start with `00_discover_providers.py` to see all supported providers and the env vars each one needs.

```bash
cd my-project
python examples/00_discover_providers.py
python examples/01_chunk_url.py
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

## Fetch Mode

The SDK supports two fetch modes, controlled by the `fetch_mode` parameter on `ScrapedatshiClient`.

### `fetch_mode="local"` (default)

The SDK fetches the URL on **your machine** using your IP address, then submits the raw HTML to our server for processing.

- ✅ Your IP is used — not our server's
- ✅ Billed at the standard per-URL rate ($0.0020)
- ✅ Faster — no double-hop latency

```python
client = ScrapedatshiClient(api_key="sds_...")  # local fetch by default
```

### `fetch_mode="server"`

Our server fetches the URL. Use this if you are behind a corporate firewall or need server-managed IP rotation.

- ⚠️ Our server's IP is used
- ⚠️ Billed at 2× the standard rate ($0.0040 / URL)
- ✅ Works from restricted environments

```python
client = ScrapedatshiClient(api_key="sds_...", fetch_mode="server")
```

---

## Chunk to JSON

No embedding or vector DB required. Returns structured JSON chunks from any source.

### Chunk a URL

```python
result = client.pipeline.chunk_url("https://docs.example.com")

print(f"Got {result.total_chunks} chunks — cost ${result.credits_used:.4f}")
for chunk in result.chunks:
    print(chunk.content[:80])
```

Optional parameters:

```python
result = client.pipeline.chunk_url(
    "https://docs.example.com/guide",
    selector="article",      # CSS selector to target main content
    chunk_size=512,           # tokens per chunk (default: 400)
    overlap=50,               # token overlap between chunks (default: 40)
    js_render=True,           # headless Chromium for SPAs
)
```

### Chunk a PDF URL

Pass any PDF URL directly — S3 links, CDN URLs, direct `.pdf` links — and the API automatically detects and extracts text. No special parameters needed.

```python
result = client.pipeline.chunk_url(
    "https://my-bucket.s3.amazonaws.com/reports/annual-report-2024.pdf"
)
print(f"Got {result.total_chunks} chunks from PDF")
```

### Chunk a local file

Supports PDF, MD, TXT, YAML, YML, and JSON. In local-fetch mode (default), the file is parsed on **your machine** — no heavy PDF processing on our server.

```python
result = client.pipeline.chunk_file("./docs/manual.pdf")
print(f"Got {result.total_chunks} chunks from {result.source}")
print(f"Cost: ${result.credits_used:.4f}")
```

| Mode | Who parses the file | OCR support | Rate |
|---|---|---|---|
| `local` (default) | Your machine | Text layer only | $0.0020 |
| `server` | Our server | Text layer + RapidOCR fallback | $0.0040 |

Use `fetch_mode="server"` for scanned/image-only PDFs that need OCR:

```python
client = ScrapedatshiClient(api_key="sds_...", fetch_mode="server")
result = client.pipeline.chunk_file("./scanned_report.pdf")  # OCR included
```

### Crawl a website

Crawls via sitemap or spider and chunks all pages. **Large sites are automatically batched server-side** — no manual pagination needed.

```python
# Sitemap crawl (default) — reads sitemap.xml
result = client.pipeline.crawl("https://docs.example.com", max_pages=20)
print(f"Crawled {result.pages_crawled} pages → {result.total_chunks} chunks")

# Spider crawl — follows links, works on any site
result = client.pipeline.crawl(
    "https://example.com",
    crawl_mode="spider",
    max_pages=10,
    include_pattern="/docs/",
    exclude_pattern="/blog/",
)

# Large sites (>200 pages) are auto-batched
if result.auto_batched:
    print(f"Auto-batched: {result.batches_processed} batches of {result.batch_size} pages")
```

---

## Authenticated Scraping (v0.10.0+)

For pages behind a login wall, pass your session cookies and/or custom headers to any fetch method. Credentials are **only sent to URLs within the permitted domain scope** — never leaked to external domains.

```python
# Scrape a login-walled page
result = client.pipeline.chunk_url(
    "https://internal.company.com/wiki/api-docs",
    cookies={"session": "abc123", "csrf": "xyz"},
    headers={"Authorization": "Bearer eyJ..."},
)

# Authenticated sitemap crawl — cookies stay on your machine
result = client.pipeline.crawl(
    "https://internal.company.com",
    cookies={"session": "abc123"},
    headers={"Authorization": "Bearer eyJ..."},
    max_pages=20,
)

# Spider crawl with subdomain scope
# Also crawls wiki.company.com, docs.company.com, etc.
result = client.pipeline.crawl(
    "https://company.com",
    crawl_mode="spider",
    cookies={"session": "abc123"},
    allow_subdomains=True,   # safe: multi-part TLDs (.co.uk) handled correctly
    max_pages=30,
)
```

**Security model:**
- Cookies and headers are **only sent to URLs within the permitted domain scope** — never to external domains discovered during crawling
- `allow_subdomains=False` (default): only the exact hostname receives credentials
- `allow_subdomains=True`: credentials are shared with subdomains of the root domain. Multi-part TLDs (`.co.uk`, `.com.br`) are handled safely.
- Credentials are **never forwarded to the scrapedatshi server** — they stay on your machine

---

## Full Pipeline — Embed + Inject

Scrape, embed, and inject directly into your vector database in one call. You bring your own embedding provider and vector DB keys (BYOK).

### Sync a URL

```python
result = client.pipeline.sync(
    url="https://docs.example.com",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="pinecone",
    vector_db_config={
        "api_key": "pc-...",
        "index_host": "https://my-index-abc123.svc.pinecone.io",
    },
)
print(f"Upserted {result.vectors_upserted} vectors ({result.total_tokens} tokens)")
print(f"Cost: ${result.credits_used:.4f}")
```

### Ingest a local file

```python
result = client.pipeline.ingest(
    file_path="./docs/manual.pdf",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="qdrant",
    vector_db_config={
        "url": "https://your-cluster.qdrant.io",
        "collection_name": "documents",
        "api_key": "qdrant-key",
    },
)
print(f"Ingested {result.chunks_created} chunks → {result.vectors_upserted} vectors")
```

### Ingest a folder (bulk import) — v0.11.0+

Bulk-ingest an entire folder of pre-scraped files into your vector database. Works with output from most scrapers — Scrapy, Playwright, Apify, custom scripts, and more. Supports `.md`, `.txt`, `.json`, `.yaml`, and `.yml`. JSON arrays are automatically detected and each item is extracted and ingested individually.

```python
result = client.pipeline.ingest_folder(
    folder_path="./scraped_output/",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="pinecone",
    vector_db_config={
        "api_key": "pc-...",
        "index_host": "https://my-index-abc123.svc.pinecone.io",
    },
)
print(f"Processed {result.files_processed} files → {result.vectors_upserted} vectors")
print(f"Failed: {result.files_failed} files")
print(f"Cost: ${result.credits_used:.4f}")
for err in result.errors:
    print(f"  ✗ {err['file']} — {err['error']}")

# Restrict to specific file types + add delay between files
result = client.pipeline.ingest_folder(
    folder_path="./",
    file_extensions=[".json"],   # only process JSON files
    batch_delay=1.0,             # 1s pause between files (rate limit safety)
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="pinecone",
    vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
)

# Async version
result = await client.pipeline.ingest_folder_async(
    folder_path="./docs/",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="qdrant",
    vector_db_config={"url": "https://...", "collection_name": "docs", "api_key": "..."},
)
```

**`IngestFolderResult` model:**

```python
result.files_processed      # int — number of files successfully ingested
result.files_failed         # int — number of files that failed
result.total_chunks         # int — total chunks created across all files
result.vectors_upserted     # int — total vectors upserted
result.credits_used         # float
result.credits_remaining    # float
result.errors               # list[dict] — [{"file": "...", "error": "..."}, ...]
```

### AutoRAG — crawl entire site → embed → inject

```python
result = client.pipeline.autorag(
    url="https://docs.example.com",
    max_pages=50,
    crawl_mode="sitemap",   # or "spider"
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="pinecone",
    vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
)
print(f"Crawled {result.pages_crawled} pages → {result.vectors_upserted} vectors")

# Large sites are auto-batched — no manual pagination needed
result = client.pipeline.autorag(
    url="https://large-docs-site.com",
    max_pages=800,  # processed as 4 batches of 200 pages each
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="pinecone",
    vector_db_config={"api_key": "pc-...", "index_host": "https://..."},
)
```

---

## Query Your Vector Database

### Inspect a vector database (free)

Use this first to confirm the dimension and embedding model used during ingestion.

```python
result = client.pipeline.inspect_vectordb(
    vector_db="pinecone",
    vector_db_config={
        "api_key": os.getenv("PINECONE_API_KEY"),
        "index_host": os.getenv("PINECONE_INDEX_HOST"),
    },
)
print(f"Dimension: {result.dimension}")
print(f"Vectors: {result.total_vector_count:,}")
print(f"Suggested models: {[m.label for m in result.suggested_models]}")
```

`inspect_vectordb()` is always free — no credits charged.

### Query a vector database

```python
result = client.pipeline.query_vectordb(
    query="How do I authenticate with the API?",
    embedding_provider="openai",
    embedding_api_key=os.getenv("OPENAI_API_KEY"),
    embedding_model="text-embedding-3-small",  # must match ingestion model
    vector_db="pinecone",
    vector_db_config={
        "api_key": os.getenv("PINECONE_API_KEY"),
        "index_host": os.getenv("PINECONE_INDEX_HOST"),
    },
    top_k=5,
)
print(f"Found {result.chunks_retrieved} results (cost: ${result.credits_used:.4f})")
for r in result.results:
    print(f"  [{r.score:.2f}] {r.text[:100]}...")
```

**Billing:** $0.0002 per chunk returned. Default `top_k=5` → $0.001 per query.

### RAG Chat — retrieve chunks and generate a grounded answer

```python
result = client.pipeline.rag_chat(
    query="How do I authenticate with the API?",
    embedding_provider="openai",
    embedding_api_key=os.getenv("OPENAI_API_KEY"),
    embedding_model="text-embedding-3-small",
    vector_db="pinecone",
    vector_db_config={
        "api_key": os.getenv("PINECONE_API_KEY"),
        "index_host": os.getenv("PINECONE_INDEX_HOST"),
    },
    llm_provider="openai",
    llm_api_key=os.getenv("OPENAI_API_KEY"),
    llm_model="gpt-4o-mini",
    top_k=5,
)
print(result.answer)
print(f"Based on {result.chunks_retrieved} chunks (cost: ${result.credits_used:.4f})")
for source in result.sources:
    print(f"  [{source.score:.2f}] {source.text[:80]}...")
```

**Billing:** $0.0002 per chunk retrieved. LLM tokens are your own cost — scrapedatshi does not bill for LLM usage.

---

## Schema Extraction

Extract structured data from any URL using your own LLM key. Define a schema and the API returns a typed JSON object.

### Extract a single object

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
    llm_model="gpt-4o-mini",
)
print(result.extracted)
# → {"title": "Widget Pro", "price": 29.99, "in_stock": True, "description": "..."}
print(f"Cost: ${result.credits_used:.4f}")
```

### Extract a list of items

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
    llm_model="gpt-4o-mini",
    extract_as_list=True,
)
print(f"Extracted {result.item_count} products")
for product in result.extracted:
    print(f"  {product['title']}: ${product['price']}")
```

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
    llm_model="gpt-4o-mini",
    max_pages=20,
    include_pattern="/products/",
)
print(f"Extracted {result.pages_extracted}/{result.pages_attempted} pages")
print(f"Cost: ${result.credits_used:.4f}")

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

---

## Contextual Retrieval (RAG 2.0)

For each chunk, an LLM generates a unique context string describing the document identity, section identity, and specific entities in that chunk. This context is prepended to the chunk text before embedding, boosting retrieval accuracy by 35–50%.

**Pricing:** `$0.0010` per chunk successfully enriched.

```python
result = client.pipeline.chunk_url(
    "https://docs.example.com",
    contextual_retrieval=True,
    llm_provider="openai",
    llm_api_key="sk-...",
    llm_model="gpt-4o-mini",
)

for chunk in result.chunks:
    print(chunk.context)        # LLM-generated context for this specific chunk
    print(chunk.original_text)  # Raw chunk text before enrichment
    print(chunk.content)        # Combined: "Context: ...\n\n{original_text}"

if result.contextual_retrieval_error:
    print(f"CR warning: {result.contextual_retrieval_error}")
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

for key, info in EMBEDDING_PROVIDERS.items():
    print(f"{key}: {info['label']}")

print(VECTOR_DB_PROVIDERS["pinecone"]["required_fields"])
# → ["api_key", "index_host"]
```

### Embedding Providers

| Key | Provider | API Key Required | Notes |
|---|---|---|---|
| `openai` | OpenAI | Yes | Common models: `text-embedding-3-small` (1536 dims), `text-embedding-3-large` (3072 dims) |
| `cohere` | Cohere | Yes | Common models: `embed-english-v3.0` (1024 dims), `embed-multilingual-v3.0` (1024 dims) |
| `gemini` | Google Gemini | Yes | Common models: `gemini-embedding-001` (3072 dims), `text-embedding-004` (768 dims) |
| `mistral` | Mistral | Yes | Model: `mistral-embed` (1024 dims) |
| `voyage` | Voyage AI | Yes | Models: `voyage-3` (1024 dims), `voyage-3-lite` (512 dims), `voyage-code-3`, `voyage-finance-2`, `voyage-law-2` |
| `ollama` | Ollama (Local) | No | Requires ngrok — see [Local Providers](#local-providers) below |

### Vector Database Providers

| Key | Provider | Required Fields | Local |
|---|---|---|---|
| `pinecone` | Pinecone | `api_key`, `index_host` | No |
| `qdrant` | Qdrant | `url`, `collection_name` | No |
| `supabase` | Supabase (pgvector) | `connection_string`, `table_name` | No |
| `weaviate` | Weaviate | `url`, `class_name` | No |
| `mongodb` | MongoDB Atlas | `connection_string`, `database_name`, `collection_name` | No |
| `azure_cosmos` | Azure Cosmos DB (NoSQL) | `connection_string`, `database_name`, `container_name` | No |
| `azure_cosmos_mongo` | Azure Cosmos DB (MongoDB API) | `connection_string`, `database_name`, `collection_name` | No |
| `chroma` | ChromaDB (Local) | `collection_name` | Yes |
| `lancedb` | LanceDB (Local) | `db_path`, `table_name` | Yes |

### LLM Providers (for Contextual Retrieval & Schema Extraction)

| Key | Provider | Document Processing Window |
|---|---|---|
| `openai` | OpenAI | Standard models (mini, etc.): 8k chars · Advanced (gpt-4o, etc.): 30k chars |
| `anthropic` | Anthropic | Standard models (haiku): 8k chars · Advanced (sonnet, opus): 30k chars |
| `gemini` | Google Gemini | Standard models (flash, lite, nano): 8k chars · Advanced (pro, etc.): 30k chars |

> **Note:** The document processing window applies to `/v1/extract` and `/v1/extract-crawl` only — it is a scrapedatshi server-side limit on how much page text is sent to the LLM, not the model's actual token limit. Use an advanced model for long-form pages.

---

## Local Providers

### Ollama (Local Embedding)

Ollama lets you run embedding models locally — no API key required. Because the scrapedatshi API server needs to reach your Ollama instance, you must expose it publicly using [ngrok](https://ngrok.com) before use.

```bash
ollama pull nomic-embed-text
ngrok http 11434
# → Forwarding: https://abc123.ngrok-free.app → localhost:11434
```

```python
result = client.pipeline.sync(
    url="https://docs.example.com",
    embedding_provider="ollama",
    embedding_api_key="",
    embedding_model="nomic-embed-text",
    embedding_endpoint="https://abc123.ngrok-free.app",
    vector_db="chroma",
    vector_db_config={"collection_name": "docs"},
)
```

### ChromaDB (Local Vector DB)

```bash
pip install chromadb
chroma run --path ./chroma_data
```

```python
result = client.pipeline.sync(
    url="https://docs.example.com",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="chroma",
    vector_db_config={
        "collection_name": "my_docs",
        "host": "localhost",
        "port": 8000,
    },
)
```

### LanceDB (Local Vector DB)

```python
result = client.pipeline.sync(
    url="https://docs.example.com",
    embedding_provider="openai",
    embedding_api_key="sk-...",
    embedding_model="text-embedding-3-small",
    vector_db="lancedb",
    vector_db_config={
        "db_path": "./lancedb",
        "table_name": "documents",
    },
)
```

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
        print(f"Processed {len(urls)} URLs → {total} chunks — total cost ${total_cost:.4f}")
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
result.credits_used            # float
result.credits_remaining       # float
```

### `Chunk`

```python
chunk.content              # str — the chunk text
chunk.token_estimate       # int — estimated token count
chunk.original_text        # str | None — raw text before CR enrichment
chunk.context              # str | None — LLM-generated per-chunk context
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

### `IngestFolderResult`

```python
result.files_processed      # int
result.files_failed         # int
result.total_chunks         # int
result.vectors_upserted     # int
result.embedding_provider   # str
result.vector_db_provider   # str
result.credits_used         # float
result.credits_remaining    # float
result.errors               # list[dict] — [{"file": "...", "error": "..."}, ...]
```

### `ExtractResult`

```python
result.extracted           # dict | list[dict]
result.field_count         # int
result.item_count          # int | None — list mode only
result.is_list             # bool
result.url                 # str
result.llm_provider        # str
result.llm_model           # str
result.schema_fields       # list[str]
result.js_render           # bool
result.content_warning     # str | None
result.credits_used        # float
result.credits_remaining   # float
```

### `ExtractCrawlResult`

```python
result.results             # list[ExtractCrawlPageResult]
result.pages_extracted     # int
result.pages_failed        # int
result.pages_attempted     # int
result.successful_results  # list[ExtractCrawlPageResult]
result.failed_results      # list[ExtractCrawlPageResult]
result.credits_used        # float
result.credits_remaining   # float
```

Each `ExtractCrawlPageResult`:

```python
page.url        # str
page.status     # "ok" | "error"
page.extracted  # dict | list[dict] | None
page.error      # str | None
page.ok         # bool
```

---

## Pricing

scrapedatshi uses a **pay-per-use credit wallet** — no subscriptions, no monthly fees.
Credits are deducted after each successful API call. Failed requests are never charged.

| Operation | Rate | Notes |
|---|---|---|
| **Per URL (local fetch)** | **$0.0020 / URL** | SDK/MCP default — your machine fetches |
| Per URL (server fetch) | $0.0040 / URL | `fetch_mode="server"` |
| Spider Fetch (server) | $0.0050 / URL | `/v1/spider` |
| Chunk Fee | $0.0005 / chunk | All routes |
| Injection Fee | $0.0030 / chunk | sync, ingest, autorag (vector DB upserts) |
| Contextual Retrieval | $0.0010 / chunk | When `contextual_retrieval=True` |
| JS Render | $0.0050 / URL | When `js_render=True` |
| Schema Extract | $0.0030 + ($0.0001 × field) | Per successfully extracted page |
| Vector Query | $0.0002 / chunk | `/v1/query`, `/v1/rag-chat` |
| Inspect Vector DB | Free | `/v1/inspect-vectordb` |

Top up your balance at [scrapedatshi.com/portal/billing](https://scrapedatshi.com/portal/billing).

---

## Hard Caps

Per-request hard caps protect server stability and apply to all accounts:

| Cap | Limit |
|---|---|
| Max pages / batch | 200 (auto-batched for larger jobs) |
| Max chunks / request | 10,000 |
| Max content size | ~75,000 words (auto-truncated) |

Content exceeding the size limit is automatically truncated — check `result.content_truncated` to detect this.

---

## Error Handling

```python
from scrapedatshi.exceptions import (
    AuthError,                 # Invalid or missing API key (401/403)
    InsufficientCreditsError,  # Balance too low (402)
    RateLimitError,            # Rate limit exceeded (429)
    ValidationError,           # Bad request payload (422)
    ServerBusyError,           # Server at capacity — retry after e.retry_after seconds (503)
    ServerError,               # API server error (5xx)
    TimeoutError,              # Request timed out
    ScrapedatshiError          # Base exception — catch-all
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

```python
import time
from scrapedatshi.exceptions import ServerBusyError

try:
    result = client.pipeline.extract_crawl(...)
except ServerBusyError as e:
    wait = e.retry_after or 30
    print(f"Server busy — retrying in {wait}s")
    time.sleep(wait)
    # retry the request...
```

---

## Troubleshooting

### Contextual Retrieval fails — deprecated or unavailable model

LLM providers periodically deprecate older models. When contextual retrieval fails due to a deprecated model, the SDK will emit a `UserWarning` automatically. Check the error programmatically:

```python
result = client.pipeline.chunk_url(
    "https://example.com",
    contextual_retrieval=True,
    llm_provider="gemini",
    llm_api_key="AIza...",
    llm_model="models/gemini-2.5-flash",  # use a current model
)
if result.contextual_retrieval_error:
    print(f"CR warning: {result.contextual_retrieval_error}")
```

**Provider model & deprecation pages:**

- OpenAI: [platform.openai.com/docs/deprecations](https://platform.openai.com/docs/deprecations)
- Anthropic: [docs.anthropic.com/en/docs/about-claude/models](https://docs.anthropic.com/en/docs/about-claude/models)
- Google Gemini: [ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)
- Cohere: [docs.cohere.com/docs/models](https://docs.cohere.com/docs/models)
- Mistral: [docs.mistral.ai/getting-started/models/](https://docs.mistral.ai/getting-started/models/)
- Voyage AI: [docs.voyageai.com/docs/embeddings](https://docs.voyageai.com/docs/embeddings)

### Contextual Retrieval fails — quota exceeded

Your LLM provider API key has no remaining credits. Note that **scrapedatshi credits and LLM provider credits are separate** — you need both.

### Suppressing contextual retrieval warnings

```python
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)
    result = client.pipeline.chunk_url(
        "https://example.com",
        contextual_retrieval=True,
        ...
    )
```

---

## Development

```bash
git clone https://github.com/scrapedatshi/scrapedatshi-py
cd scrapedatshi-py
pip install -e ".[dev]"
pytest
```

---

## License

MIT — see [LICENSE](https://github.com/scrapedatshi/scrapedatshi-py/blob/main/LICENSE).
