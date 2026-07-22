"""
scrapedatshi.pipeline._extract
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Schema extraction methods: extract and extract_crawl.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scrapedatshi.client import ScrapedatshiClient

from scrapedatshi.models import (
    ExtractCrawlPageResult,
    ExtractCrawlResult,
    ExtractResult,
)


def _parse_extract_crawl_result(data: dict) -> ExtractCrawlResult:
    """Parse the /v1/extract-crawl response into an ExtractCrawlResult model."""
    raw_results = data.get("results", [])
    page_results = [
        ExtractCrawlPageResult(
            url=r.get("url", ""),
            status=r.get("status", "error"),
            extracted=r.get("extracted"),
            error=r.get("error"),
        )
        for r in raw_results
    ]

    pages_attempted = data.get("pages_attempted", len(raw_results))
    pages_extracted = data.get("pages_extracted", sum(1 for r in page_results if r.ok))
    pages_failed = data.get("pages_failed", sum(1 for r in page_results if not r.ok))

    return ExtractCrawlResult(
        results=page_results,
        pages_extracted=pages_extracted,
        pages_failed=pages_failed,
        pages_attempted=pages_attempted,
        pages_discovered=data.get("pages_discovered", pages_attempted),
        root_url=data.get("root_url", ""),
        crawl_mode=data.get("crawl_mode", "sitemap"),
        field_count=data.get("field_count", 0),
        llm_provider=data.get("llm_provider", ""),
        llm_model=data.get("llm_model", ""),
        extract_as_list=bool(data.get("extract_as_list", False)),
        job_id=data.get("job_id"),
        credits_used=float(data.get("credits_used", 0.0)),
        credits_remaining=float(data.get("credits_remaining", 0.0)),
    )


class ExtractMixin:
    """Mixin providing extract and extract_crawl methods."""

    _client: "ScrapedatshiClient"

    # ── Schema Extraction ─────────────────────────────────────────────────────

    def extract(
        self,
        url: str,
        *,
        schema: dict[str, str],
        llm_provider: str,
        llm_api_key: str,
        llm_model: str | None = None,
        selector: str | None = None,
        extract_as_list: bool = False,
        js_render: bool = False,
        click_selector: str | None = None,
    ) -> ExtractResult:
        """
        Scrape a URL and extract structured data matching your schema using an LLM.
        """
        payload: dict = {
            "url": url,
            "schema": schema,
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
        }
        if llm_model:
            payload["llm_model"] = llm_model
        if selector:
            payload["selector"] = selector
        if extract_as_list:
            payload["extract_as_list"] = True
        if js_render:
            payload["js_render"] = True
        if click_selector:
            payload["click_selector"] = click_selector

        data = self._client._post("/v1/extract", json=payload)

        extracted = data.get("extracted", {})
        item_count = data.get("item_count")
        if item_count is None and isinstance(extracted, list):
            item_count = len(extracted)

        return ExtractResult(
            extracted=extracted,
            field_count=data.get("field_count", len(schema)),
            item_count=item_count,
            url=url,
            llm_provider=llm_provider,
            llm_model=data.get(
                "llm_model", llm_model or f"(default for {llm_provider})"
            ),
            schema_fields=data.get("schema_fields", list(schema.keys())),
            js_render=js_render,
            content_warning=data.get("content_warning"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    async def extract_async(
        self,
        url: str,
        *,
        schema: dict[str, str],
        llm_provider: str,
        llm_api_key: str,
        llm_model: str | None = None,
        selector: str | None = None,
        extract_as_list: bool = False,
        js_render: bool = False,
        click_selector: str | None = None,
    ) -> ExtractResult:
        """Async version of :meth:`extract`."""
        payload: dict = {
            "url": url,
            "schema": schema,
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
        }
        if llm_model:
            payload["llm_model"] = llm_model
        if selector:
            payload["selector"] = selector
        if extract_as_list:
            payload["extract_as_list"] = True
        if js_render:
            payload["js_render"] = True
        if click_selector:
            payload["click_selector"] = click_selector

        data = await self._client._post_async("/v1/extract", json=payload)

        extracted = data.get("extracted", {})
        item_count = data.get("item_count")
        if item_count is None and isinstance(extracted, list):
            item_count = len(extracted)

        return ExtractResult(
            extracted=extracted,
            field_count=data.get("field_count", len(schema)),
            item_count=item_count,
            url=url,
            llm_provider=llm_provider,
            llm_model=data.get(
                "llm_model", llm_model or f"(default for {llm_provider})"
            ),
            schema_fields=data.get("schema_fields", list(schema.keys())),
            js_render=js_render,
            content_warning=data.get("content_warning"),
            credits_used=float(data.get("credits_used", 0.0)),
            credits_remaining=float(data.get("credits_remaining", 0.0)),
        )

    # ── Schema Extraction via Crawl ───────────────────────────────────────────

    def extract_crawl(
        self,
        url: str,
        *,
        schema: dict[str, str],
        llm_provider: str,
        llm_api_key: str,
        llm_model: str | None = None,
        crawl_mode: str = "sitemap",
        max_pages: int = 5,
        selector: str | None = None,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        extract_as_list: bool = False,
        llm_rpm: int | None = None,
    ) -> ExtractCrawlResult:
        """
        Crawl a domain and extract structured data from every page using your LLM.

        Args:
            llm_rpm: Optional rate limit in requests-per-minute for LLM calls.
                     Use this to avoid hitting provider rate limits, e.g.:
                       - llm_rpm=10  for Gemini free / Tier-1
                       - llm_rpm=60  for OpenAI Tier-1
                     When omitted the server uses a short jittered politeness delay.
        """
        payload: dict = {
            "url": url,
            "schema": schema,
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
            "crawl_mode": crawl_mode,
            "max_pages": max_pages,
        }
        if llm_model:
            payload["llm_model"] = llm_model
        if selector:
            payload["selector"] = selector
        if include_pattern:
            payload["include_pattern"] = include_pattern
        if exclude_pattern:
            payload["exclude_pattern"] = exclude_pattern
        if extract_as_list:
            payload["extract_as_list"] = True
        if llm_rpm is not None:
            payload["llm_rpm"] = llm_rpm

        data = self._client._post("/v1/extract-crawl", json=payload)
        return _parse_extract_crawl_result(data)

    async def extract_crawl_async(
        self,
        url: str,
        *,
        schema: dict[str, str],
        llm_provider: str,
        llm_api_key: str,
        llm_model: str | None = None,
        crawl_mode: str = "sitemap",
        max_pages: int = 5,
        selector: str | None = None,
        include_pattern: str | None = None,
        exclude_pattern: str | None = None,
        extract_as_list: bool = False,
        llm_rpm: int | None = None,
    ) -> ExtractCrawlResult:
        """Async version of :meth:`extract_crawl`.

        Args:
            llm_rpm: Optional rate limit in requests-per-minute for LLM calls.
                     Use this to avoid hitting provider rate limits, e.g.:
                       - llm_rpm=10  for Gemini free / Tier-1
                       - llm_rpm=60  for OpenAI Tier-1
                     When omitted the server uses a short jittered politeness delay.
        """
        payload: dict = {
            "url": url,
            "schema": schema,
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
            "crawl_mode": crawl_mode,
            "max_pages": max_pages,
        }
        if llm_model:
            payload["llm_model"] = llm_model
        if selector:
            payload["selector"] = selector
        if include_pattern:
            payload["include_pattern"] = include_pattern
        if exclude_pattern:
            payload["exclude_pattern"] = exclude_pattern
        if extract_as_list:
            payload["extract_as_list"] = True
        if llm_rpm is not None:
            payload["llm_rpm"] = llm_rpm

        data = await self._client._post_async("/v1/extract-crawl", json=payload)
        return _parse_extract_crawl_result(data)
