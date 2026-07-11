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
    InsufficientCreditsError,
    RateLimitError,
    ScrapedatshiError,
    ServerBusyError,
    ServerError,
    TierError,  # kept for backward compatibility — no longer raised by the API
    TimeoutError,
    ValidationError,
)
from scrapedatshi.pipeline import PipelineNamespace

# Default production API base URL
_DEFAULT_BASE_URL = "https://api.scrapedatshi.com"

# Default timeouts (seconds)
_DEFAULT_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

# Timeout used for local URL fetches (client-side, before submitting HTML to the API)
_LOCAL_FETCH_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

# User-Agent for local fetches — identifies the SDK to target sites
_LOCAL_FETCH_USER_AGENT = "scrapedatshi-py/0.8.0 (+https://scrapedatshi.com/bot)"


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
        fetch_mode: ``"local"`` (default) or ``"server"``.
                    ``"local"`` — the SDK fetches URLs using the caller's IP address
                    and submits the raw HTML to the API for processing. This is the
                    default and is billed at the standard per-URL rate.
                    ``"server"`` — the API server fetches the URL (legacy behaviour).
                    Billed at 2× the standard per-URL rate. Use this if you are behind
                    a firewall or need server-managed IP rotation.

    Raises:
        :class:`~scrapedatshi.exceptions.AuthError`: If no API key is provided.

    Example::

        # Sync (local fetch — default, uses your IP)
        client = ScrapedatshiClient(api_key="sds_...")
        result = client.pipeline.chunk_url("https://docs.example.com")

        # Sync (server fetch — legacy, uses our server's IP)
        client = ScrapedatshiClient(api_key="sds_...", fetch_mode="server")
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
        fetch_mode: str = "local",
    ) -> None:
        resolved_key = api_key or os.environ.get("SCRAPEDATSHI_API_KEY")
        if not resolved_key:
            raise AuthError(
                "No API key provided. Pass api_key= or set the "
                "SCRAPEDATSHI_API_KEY environment variable."
            )

        if fetch_mode not in ("local", "server"):
            raise ValueError("fetch_mode must be 'local' or 'server'.")

        self._api_key = resolved_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self.fetch_mode = fetch_mode

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

    # ── Local URL fetch helpers ───────────────────────────────────────────────

    def _fetch_url_locally(self, url: str) -> str:
        """
        Fetch a URL synchronously using the caller's machine and IP address.

        Returns the raw HTML string.  Used by local-fetch mode (the default).
        The request uses a neutral User-Agent that identifies the SDK.

        Raises:
            :class:`~scrapedatshi.exceptions.ScrapedatshiError`: On network failure.
            :class:`~scrapedatshi.exceptions.TimeoutError`: If the request times out.
        """
        headers = {"User-Agent": _LOCAL_FETCH_USER_AGENT}
        try:
            with httpx.Client(
                timeout=_LOCAL_FETCH_TIMEOUT, follow_redirects=True
            ) as client:
                response = client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Local fetch of {url} timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise ScrapedatshiError(
                f"Local fetch of {url} returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise ScrapedatshiError(f"Local fetch of {url} failed: {exc}") from exc

    async def _fetch_url_locally_async(self, url: str) -> str:
        """
        Async version of :meth:`_fetch_url_locally`.
        """
        headers = {"User-Agent": _LOCAL_FETCH_USER_AGENT}
        try:
            async with httpx.AsyncClient(
                timeout=_LOCAL_FETCH_TIMEOUT, follow_redirects=True
            ) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                return response.text
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Local fetch of {url} timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise ScrapedatshiError(
                f"Local fetch of {url} returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise ScrapedatshiError(f"Local fetch of {url} failed: {exc}") from exc

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
        return (
            f"ScrapedatshiClient(api_key={masked!r}, base_url={self._base_url!r}, "
            f"fetch_mode={self.fetch_mode!r})"
        )


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

    if status == 402:
        raise InsufficientCreditsError(
            detail
            or "Insufficient credits. Top up at scrapedatshi.com/portal/billing.",
            status_code=status,
        )

    if status in (401, 403):
        raise AuthError(detail, status_code=status)

    if status == 422:
        raise ValidationError(detail, status_code=status)

    if status == 429:
        raise RateLimitError(detail, status_code=status)

    if status == 503:
        # Server is temporarily at capacity — extract Retry-After header
        retry_after: int | None = None
        try:
            raw = response.headers.get("Retry-After")
            if raw:
                retry_after = int(raw)
        except (ValueError, TypeError):
            pass
        raise ServerBusyError(
            detail or "Server is temporarily at capacity. Please retry shortly.",
            status_code=status,
            retry_after=retry_after,
        )

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
