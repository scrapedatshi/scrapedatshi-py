"""
scrapedatshi.client
~~~~~~~~~~~~~~~~~~~
ScrapedatshiClient — the main entry point for the scrapedatshi SDK.

Usage (sync)::

    from scrapedatshi import ScrapedatshiClient

    client = ScrapedatshiClient(api_key="sds_...")
    result = client.pipeline.chunk_url("https://docs.example.com")

Usage (async context manager)::

    async with ScrapedatshiClient(api_key="sds_...") as client:
        result = await client.pipeline.chunk_url_async("https://docs.example.com")
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from scrapedatshi.exceptions import (
    AuthError,
    RateLimitError,
    ScrapedatshiError,
    ServerError,
    TierError,
    TimeoutError,
    ValidationError,
)
from scrapedatshi.pipeline import PipelineNamespace

# Default production API base URL
_DEFAULT_BASE_URL = "https://api.scrapedatshi.com"

# Default timeouts (seconds)
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


class ScrapedatshiClient:
    """
    The main scrapedatshi API client.

    Provides both synchronous and asynchronous access to all pipeline endpoints.
    Namespaces:
        - ``client.pipeline`` — all pipeline operations

    Args:
        api_key: Your scrapedatshi API key (``sds_...``).
                 Falls back to the ``SCRAPEDATSHI_API_KEY`` environment variable.
        base_url: Override the API base URL (useful for self-hosted or staging).
        timeout: Custom :class:`httpx.Timeout` instance.

    Raises:
        :class:`~scrapedatshi.exceptions.AuthError`: If no API key is provided.

    Example::

        # Sync
        client = ScrapedatshiClient(api_key="sds_...")
        result = client.pipeline.chunk_url("https://docs.example.com")

        # Async context manager
        async with ScrapedatshiClient(api_key="sds_...") as client:
            result = await client.pipeline.chunk_url_async("https://docs.example.com")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: httpx.Timeout = _DEFAULT_TIMEOUT,
    ) -> None:
        resolved_key = api_key or os.environ.get("SCRAPEDATSHI_API_KEY")
        if not resolved_key:
            raise AuthError(
                "No API key provided. Pass api_key= or set the "
                "SCRAPEDATSHI_API_KEY environment variable."
            )

        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

        # Shared headers for all requests
        self._headers = {
            "X-API-Key": self._api_key,
            "Accept": "application/json",
            "User-Agent": f"scrapedatshi-py/{_get_version()}",
        }

        # Lazy-initialised httpx clients
        self._sync_client: httpx.Client | None = None
        self._async_client: httpx.AsyncClient | None = None

        # Namespaces
        self.pipeline = PipelineNamespace(self)

    # ── Sync HTTP helpers ─────────────────────────────────────────────────────

    def _get_sync_client(self) -> httpx.Client:
        if self._sync_client is None or self._sync_client.is_closed:
            self._sync_client = httpx.Client(
                base_url=self._base_url,
                headers=self._headers,
                timeout=self._timeout,
            )
        return self._sync_client

    def _post(
        self,
        path: str,
        *,
        json: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
    ) -> dict[str, Any]:
        """Execute a synchronous POST request and return the parsed JSON body."""
        client = self._get_sync_client()
        try:
            response = client.post(path, json=json, files=files, data=data)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Request to {path} timed out.") from exc
        except httpx.RequestError as exc:
            raise ScrapedatshiError(f"Network error on {path}: {exc}") from exc

        return _handle_response(response)

    def close(self) -> None:
        """Close the underlying sync httpx client. Call when done in non-context-manager usage."""
        if self._sync_client and not self._sync_client.is_closed:
            self._sync_client.close()

    # ── Async HTTP helpers ────────────────────────────────────────────────────

    def _get_async_client(self) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers,
                timeout=self._timeout,
            )
        return self._async_client

    async def _post_async(
        self,
        path: str,
        *,
        json: dict | None = None,
        files: dict | None = None,
        data: dict | None = None,
    ) -> dict[str, Any]:
        """Execute an asynchronous POST request and return the parsed JSON body."""
        client = self._get_async_client()
        try:
            response = await client.post(path, json=json, files=files, data=data)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Request to {path} timed out.") from exc
        except httpx.RequestError as exc:
            raise ScrapedatshiError(f"Network error on {path}: {exc}") from exc

        return _handle_response(response)

    async def aclose(self) -> None:
        """Close the underlying async httpx client."""
        if self._async_client and not self._async_client.is_closed:
            await self._async_client.aclose()

    # ── Context manager support ───────────────────────────────────────────────

    def __enter__(self) -> "ScrapedatshiClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    async def __aenter__(self) -> "ScrapedatshiClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        masked = self._api_key[:8] + "..." if len(self._api_key) > 8 else "***"
        return f"ScrapedatshiClient(api_key={masked!r}, base_url={self._base_url!r})"


# ── Response handler ──────────────────────────────────────────────────────────


def _handle_response(response: httpx.Response) -> dict[str, Any]:
    """
    Parse an httpx response, raising typed exceptions for error status codes.
    Returns the parsed JSON body on success.
    """
    if response.is_success:
        try:
            return response.json()
        except Exception:
            return {"raw": response.text}

    # Try to extract a detail message from the response body
    try:
        body = response.json()
        detail = body.get("detail", response.text)
    except Exception:
        detail = response.text

    status = response.status_code

    if status in (401, 403):
        # Distinguish tier errors from auth errors
        if (
            "tier" in detail.lower()
            or "upgrade" in detail.lower()
            or "plan" in detail.lower()
        ):
            raise TierError(detail, status_code=status)
        raise AuthError(detail, status_code=status)

    if status == 422:
        raise ValidationError(detail, status_code=status)

    if status == 429:
        raise RateLimitError(detail, status_code=status)

    if status >= 500:
        raise ServerError(detail, status_code=status)

    raise ScrapedatshiError(detail, status_code=status)


# ── Version helper ────────────────────────────────────────────────────────────


def _get_version() -> str:
    try:
        from importlib.metadata import version

        return version("scrapedatshi")
    except Exception:
        return "0.0.0"
