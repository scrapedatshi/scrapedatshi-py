"""
scrapedatshi.pipeline._crawl_helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Local crawl engine — sitemap discovery and spider BFS.

These helpers run on the CLIENT machine (local-fetch mode).
They are used by chunk_url (crawl mode) and the crawl() method.

No credentials are passed to sitemap fetches — sitemaps are public assets.
Cookies/headers are only forwarded to URLs within the permitted domain scope.
"""

from __future__ import annotations

import re
import time
from html.parser import HTMLParser
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi._domain_utils import _is_matching_domain_scope
from scrapedatshi.models import CrawlChunkResult

# ── Constants ─────────────────────────────────────────────────────────────────

# File extensions to skip during local crawls (same as server-side filter_urls)
_SKIP_EXTENSIONS = (
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".gifv",
    ".webp",
    ".mp4",
    ".avi",
    ".mov",
    ".svg",
    ".css",
    ".js",
    ".zip",
    ".tar",
    ".gz",
    ".xml",
    ".json",
    ".txt",
)

# Politeness delay between page fetches (seconds)
_CRAWL_POLITENESS_DELAY = 0.5

# User-Agent for sitemap fetches
_SITEMAP_USER_AGENT = "scrapedatshi-py/0.12.0 (+https://scrapedatshi.com/bot)"


# ── Link harvester ────────────────────────────────────────────────────────────


class _LinkHarvester(HTMLParser):
    """Minimal HTML parser that extracts href values from <a> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            for attr, value in attrs:
                if attr == "href" and value:
                    self.links.append(value)


# ── Sitemap helpers ───────────────────────────────────────────────────────────


def _parse_sitemap_urls(text: str) -> list[str]:
    """
    Parse a sitemap XML string and return all <loc> URLs.
    Handles both <urlset> (regular) and <sitemapindex> (nested) formats.
    Falls back to regex extraction if XML parsing fails.
    """
    try:
        text_clean = re.sub(r"\s+xmlns[^>]*", "", text)
        root = ElementTree.fromstring(text_clean)
        return [loc.text.strip() for loc in root.findall(".//loc") if loc.text]
    except ElementTree.ParseError:
        return re.findall(r"<loc>(.*?)</loc>", text)


def _fetch_sitemap_text(root_url: str) -> str | None:
    """
    Synchronously fetch a sitemap from the root domain.
    Tries /sitemap.xml, /sitemap_index.xml, then robots.txt Sitemap: directive.
    Returns the raw XML text, or None if nothing found.
    """
    import httpx as _httpx

    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {"User-Agent": _SITEMAP_USER_AGENT}

    try:
        with _httpx.Client(timeout=15.0, follow_redirects=True) as client:
            for path in ("/sitemap.xml", "/sitemap_index.xml"):
                try:
                    resp = client.get(base + path, headers=headers)
                    if resp.status_code == 200 and (
                        "<urlset" in resp.text or "<sitemapindex" in resp.text
                    ):
                        return resp.text
                except Exception:
                    continue

            try:
                resp = client.get(base + "/robots.txt", headers=headers)
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        if line.lower().startswith("sitemap:"):
                            sitemap_url = line.split(":", 1)[1].strip()
                            try:
                                resp2 = client.get(sitemap_url, headers=headers)
                                if resp2.status_code == 200:
                                    return resp2.text
                            except Exception:
                                pass
            except Exception:
                pass
    except Exception:
        pass

    return None


async def _fetch_sitemap_text_async(root_url: str) -> str | None:
    """Async version of :func:`_fetch_sitemap_text`."""
    import httpx as _httpx

    parsed = urlparse(root_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    headers = {"User-Agent": _SITEMAP_USER_AGENT}

    try:
        async with _httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for path in ("/sitemap.xml", "/sitemap_index.xml"):
                try:
                    resp = await client.get(base + path, headers=headers)
                    if resp.status_code == 200 and (
                        "<urlset" in resp.text or "<sitemapindex" in resp.text
                    ):
                        return resp.text
                except Exception:
                    continue

            try:
                resp = await client.get(base + "/robots.txt", headers=headers)
                if resp.status_code == 200:
                    for line in resp.text.splitlines():
                        if line.lower().startswith("sitemap:"):
                            sitemap_url = line.split(":", 1)[1].strip()
                            try:
                                resp2 = await client.get(sitemap_url, headers=headers)
                                if resp2.status_code == 200:
                                    return resp2.text
                            except Exception:
                                pass
            except Exception:
                pass
    except Exception:
        pass

    return None


def _filter_crawl_urls(
    urls: list[str],
    root_url: str,
    include_pattern: str | None,
    exclude_pattern: str | None,
    max_pages: int,
    allow_subdomains: bool,
) -> list[str]:
    """Filter a list of discovered URLs for local crawl."""
    seen: set[str] = set()
    filtered: list[str] = []

    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)

        if not _is_matching_domain_scope(url, root_url, allow_subdomains):
            continue

        if include_pattern and include_pattern not in url:
            continue
        if exclude_pattern and exclude_pattern in url:
            continue

        if any(url.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
            continue

        filtered.append(url)
        if len(filtered) >= max_pages:
            break

    return filtered


# ── Page chunking helpers ─────────────────────────────────────────────────────


def _chunk_page_locally(
    client: "ScrapedatshiClient",
    page_url: str,
    html: str,
    selector: str | None,
    chunk_size: int,
    overlap: int,
    contextual_retrieval: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
) -> tuple[list[dict], float, float]:
    """Submit pre-fetched HTML to /v1/rag-chunk and return (chunks, credits_used, credits_remaining)."""
    payload: dict = {"url": page_url, "html": html}
    if selector:
        payload["selector"] = selector
    if chunk_size != 512:
        payload["chunk_size"] = chunk_size
    if overlap != 50:
        payload["overlap"] = overlap
    if contextual_retrieval:
        payload["contextual_retrieval"] = True
        if llm_provider:
            payload["llm_provider"] = llm_provider
        if llm_api_key:
            payload["llm_api_key"] = llm_api_key
        if llm_model:
            payload["llm_model"] = llm_model

    try:
        data = client._post("/v1/rag-chunk", json=payload)
        return (
            data.get("chunks", []),
            float(data.get("credits_used", 0.0)),
            float(data.get("credits_remaining", 0.0)),
        )
    except Exception:
        return [], 0.0, 0.0


async def _chunk_page_locally_async(
    client: "ScrapedatshiClient",
    page_url: str,
    html: str,
    selector: str | None,
    chunk_size: int,
    overlap: int,
    contextual_retrieval: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
) -> tuple[list[dict], float, float]:
    """Async version of :func:`_chunk_page_locally`."""
    payload: dict = {"url": page_url, "html": html}
    if selector:
        payload["selector"] = selector
    if chunk_size != 512:
        payload["chunk_size"] = chunk_size
    if overlap != 50:
        payload["overlap"] = overlap
    if contextual_retrieval:
        payload["contextual_retrieval"] = True
        if llm_provider:
            payload["llm_provider"] = llm_provider
        if llm_api_key:
            payload["llm_api_key"] = llm_api_key
        if llm_model:
            payload["llm_model"] = llm_model

    try:
        data = await client._post_async("/v1/rag-chunk", json=payload)
        return (
            data.get("chunks", []),
            float(data.get("credits_used", 0.0)),
            float(data.get("credits_remaining", 0.0)),
        )
    except Exception:
        return [], 0.0, 0.0


# ── Playwright local fetch helper ────────────────────────────────────────────


def _fetch_url_with_playwright_sync(url: str) -> str:
    """
    Fetch a URL using a local headless Playwright browser (synchronous wrapper).

    Used by _crawl_locally when js_render=True. Runs Playwright in a new event
    loop so it can be called from synchronous code.

    Requires: pip install playwright && playwright install chromium
    """
    import asyncio as _asyncio

    try:
        from playwright.async_api import async_playwright  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "playwright is required for js_render=True on crawl. "
            "Install it with: pip install playwright && playwright install chromium"
        )

    async def _fetch() -> str:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            try:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/125.0.0.0 Safari/537.36"
                    )
                )
                page = await context.new_page()
                await page.goto(url, wait_until="load", timeout=30000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                await page.wait_for_timeout(500)
                return await page.content()
            finally:
                await browser.close()

    try:
        loop = _asyncio.get_event_loop()
        if loop.is_running():
            # Already inside an event loop (e.g. Jupyter) — use a thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_asyncio.run, _fetch())
                return future.result()
        else:
            return loop.run_until_complete(_fetch())
    except RuntimeError:
        return _asyncio.run(_fetch())


# ── Local crawl loops ─────────────────────────────────────────────────────────


def _crawl_locally(
    *,
    client: "ScrapedatshiClient",
    url: str,
    crawl_mode: str,
    max_pages: int,
    selector: str | None,
    include_pattern: str | None,
    exclude_pattern: str | None,
    js_render: bool = False,
    contextual_retrieval: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
    cookies: dict | None,
    headers: dict | None,
    allow_subdomains: bool,
) -> "CrawlChunkResult":
    """
    Synchronous local crawl loop.

    Discovers URLs (sitemap or spider BFS), fetches each page on the caller's
    machine, and submits HTML to /v1/rag-chunk for chunking.

    When js_render=True, each page is fetched using a local headless Playwright
    browser instead of httpx. Playwright must be installed:
        pip install playwright && playwright install chromium
    """
    all_chunks: list[dict] = []
    total_credits_used: float = 0.0
    last_credits_remaining: float = 0.0
    pages_crawled: int = 0

    if crawl_mode == "sitemap":
        sitemap_text = _fetch_sitemap_text(url)
        if sitemap_text:
            discovered = _parse_sitemap_urls(sitemap_text)
        else:
            discovered = [url]

        urls_to_crawl = _filter_crawl_urls(
            discovered,
            url,
            include_pattern,
            exclude_pattern,
            max_pages,
            allow_subdomains,
        )

        for page_url in urls_to_crawl:
            send_creds = _is_matching_domain_scope(page_url, url, allow_subdomains)
            try:
                if js_render:
                    html = _fetch_url_with_playwright_sync(page_url)
                else:
                    html = client._fetch_url_locally(
                        page_url,
                        cookies=cookies if send_creds else None,
                        extra_headers=headers if send_creds else None,
                    )
            except Exception:
                time.sleep(_CRAWL_POLITENESS_DELAY)
                continue

            chunks, credits_used, credits_remaining = _chunk_page_locally(
                client=client,
                page_url=page_url,
                html=html,
                selector=selector,
                chunk_size=512,
                overlap=50,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )
            all_chunks.extend(chunks)
            total_credits_used += credits_used
            last_credits_remaining = credits_remaining
            pages_crawled += 1
            time.sleep(_CRAWL_POLITENESS_DELAY)

    else:
        # Spider mode (BFS)
        visited: set[str] = set()
        queue: list[str] = [url]

        while queue and pages_crawled < max_pages:
            page_url = queue.pop(0)
            normalized = page_url.split("#")[0].rstrip("/")
            if not normalized or normalized in visited:
                continue
            if not _is_matching_domain_scope(normalized, url, allow_subdomains):
                continue
            if include_pattern and include_pattern not in normalized:
                continue
            if exclude_pattern and exclude_pattern in normalized:
                continue
            if any(normalized.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue

            visited.add(normalized)
            send_creds = _is_matching_domain_scope(normalized, url, allow_subdomains)
            try:
                if js_render:
                    html = _fetch_url_with_playwright_sync(normalized)
                else:
                    html = client._fetch_url_locally(
                        normalized,
                        cookies=cookies if send_creds else None,
                        extra_headers=headers if send_creds else None,
                    )
            except Exception:
                time.sleep(_CRAWL_POLITENESS_DELAY)
                continue

            harvester = _LinkHarvester()
            harvester.feed(html)
            for href in harvester.links:
                absolute = urljoin(normalized, href).split("#")[0].rstrip("/")
                if (
                    absolute
                    and absolute not in visited
                    and absolute not in queue
                    and _is_matching_domain_scope(absolute, url, allow_subdomains)
                    and not any(
                        absolute.lower().endswith(ext) for ext in _SKIP_EXTENSIONS
                    )
                ):
                    queue.append(absolute)

            chunks, credits_used, credits_remaining = _chunk_page_locally(
                client=client,
                page_url=normalized,
                html=html,
                selector=selector,
                chunk_size=512,
                overlap=50,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )
            all_chunks.extend(chunks)
            total_credits_used += credits_used
            last_credits_remaining = credits_remaining
            pages_crawled += 1
            time.sleep(_CRAWL_POLITENESS_DELAY)

    return CrawlChunkResult(
        chunks=all_chunks,
        total_chunks=len(all_chunks),
        pages_crawled=pages_crawled,
        source_url=url,
        contextual_retrieval_used=contextual_retrieval,
        contextual_retrieval_error=None,
        credits_used=total_credits_used,
        credits_remaining=last_credits_remaining,
    )


async def _crawl_locally_async(
    *,
    client: "ScrapedatshiClient",
    url: str,
    crawl_mode: str,
    max_pages: int,
    selector: str | None,
    include_pattern: str | None,
    exclude_pattern: str | None,
    js_render: bool = False,
    contextual_retrieval: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None,
    cookies: dict | None,
    headers: dict | None,
    allow_subdomains: bool,
) -> "CrawlChunkResult":
    """Async version of :func:`_crawl_locally`."""
    import asyncio as _asyncio

    all_chunks: list[dict] = []
    total_credits_used: float = 0.0
    last_credits_remaining: float = 0.0
    pages_crawled: int = 0

    if crawl_mode == "sitemap":
        sitemap_text = await _fetch_sitemap_text_async(url)
        if sitemap_text:
            discovered = _parse_sitemap_urls(sitemap_text)
        else:
            discovered = [url]

        urls_to_crawl = _filter_crawl_urls(
            discovered,
            url,
            include_pattern,
            exclude_pattern,
            max_pages,
            allow_subdomains,
        )

        for page_url in urls_to_crawl:
            send_creds = _is_matching_domain_scope(page_url, url, allow_subdomains)
            try:
                if js_render:
                    html = await _asyncio.to_thread(
                        _fetch_url_with_playwright_sync, page_url
                    )
                else:
                    html = await client._fetch_url_locally_async(
                        page_url,
                        cookies=cookies if send_creds else None,
                        extra_headers=headers if send_creds else None,
                    )
            except Exception:
                await _asyncio.sleep(_CRAWL_POLITENESS_DELAY)
                continue

            chunks, credits_used, credits_remaining = await _chunk_page_locally_async(
                client=client,
                page_url=page_url,
                html=html,
                selector=selector,
                chunk_size=512,
                overlap=50,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )
            all_chunks.extend(chunks)
            total_credits_used += credits_used
            last_credits_remaining = credits_remaining
            pages_crawled += 1
            await _asyncio.sleep(_CRAWL_POLITENESS_DELAY)

    else:
        # Spider mode (BFS)
        visited: set[str] = set()
        queue: list[str] = [url]

        while queue and pages_crawled < max_pages:
            page_url = queue.pop(0)
            normalized = page_url.split("#")[0].rstrip("/")
            if not normalized or normalized in visited:
                continue
            if not _is_matching_domain_scope(normalized, url, allow_subdomains):
                continue
            if include_pattern and include_pattern not in normalized:
                continue
            if exclude_pattern and exclude_pattern in normalized:
                continue
            if any(normalized.lower().endswith(ext) for ext in _SKIP_EXTENSIONS):
                continue

            visited.add(normalized)
            send_creds = _is_matching_domain_scope(normalized, url, allow_subdomains)
            try:
                if js_render:
                    html = await _asyncio.to_thread(
                        _fetch_url_with_playwright_sync, normalized
                    )
                else:
                    html = await client._fetch_url_locally_async(
                        normalized,
                        cookies=cookies if send_creds else None,
                        extra_headers=headers if send_creds else None,
                    )
            except Exception:
                await _asyncio.sleep(_CRAWL_POLITENESS_DELAY)
                continue

            harvester = _LinkHarvester()
            harvester.feed(html)
            for href in harvester.links:
                absolute = urljoin(normalized, href).split("#")[0].rstrip("/")
                if (
                    absolute
                    and absolute not in visited
                    and absolute not in queue
                    and _is_matching_domain_scope(absolute, url, allow_subdomains)
                    and not any(
                        absolute.lower().endswith(ext) for ext in _SKIP_EXTENSIONS
                    )
                ):
                    queue.append(absolute)

            chunks, credits_used, credits_remaining = await _chunk_page_locally_async(
                client=client,
                page_url=normalized,
                html=html,
                selector=selector,
                chunk_size=512,
                overlap=50,
                contextual_retrieval=contextual_retrieval,
                llm_provider=llm_provider,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )
            all_chunks.extend(chunks)
            total_credits_used += credits_used
            last_credits_remaining = credits_remaining
            pages_crawled += 1
            await _asyncio.sleep(_CRAWL_POLITENESS_DELAY)

    return CrawlChunkResult(
        chunks=all_chunks,
        total_chunks=len(all_chunks),
        pages_crawled=pages_crawled,
        source_url=url,
        contextual_retrieval_used=contextual_retrieval,
        contextual_retrieval_error=None,
        credits_used=total_credits_used,
        credits_remaining=last_credits_remaining,
    )
