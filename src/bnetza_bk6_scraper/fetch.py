"""Polite async HTTP client for the BNetzA site."""

from __future__ import annotations

import asyncio

import aiohttp

# BNetzA's WAF blocks non-browser User-Agents (returns a 200 "URL was rejected" page).
# A browser-like UA + Accept headers are required to receive real content.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}
_TRANSIENT = {429, 500, 502, 503, 504}
_WAF_BLOCK_MARKER = "The requested URL was rejected"
# aiohttp's default total timeout is 5 minutes; cap it so a stuck request retries.
_TIMEOUT = aiohttp.ClientTimeout(total=60)


class WafBlockedError(aiohttp.ClientError):
    """Raised when the WAF returns its 200-status rejection page, so it is retried."""


class Fetcher:
    """Bounded-concurrency aiohttp wrapper with retry/backoff."""

    def __init__(
        self, concurrency: int = 4, max_retries: int = 3, backoff_seconds: float = 1.0
    ) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "Fetcher":
        self._session = aiohttp.ClientSession(headers=_HEADERS, timeout=_TIMEOUT)
        return self

    async def __aexit__(self, *exc: object) -> None:
        assert self._session is not None
        await self._session.close()

    async def _fetch(self, url: str, as_text: bool) -> str | bytes:
        """GET with retry/backoff. Reads the body inside the loop so the WAF 200-block
        page (only detectable in the body of a text response) can be retried too."""
        assert self._session is not None
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            async with self._semaphore:
                try:
                    async with self._session.get(url) as resp:
                        if resp.status in _TRANSIENT:
                            raise aiohttp.ClientResponseError(
                                resp.request_info, resp.history, status=resp.status
                            )
                        resp.raise_for_status()
                        if as_text:
                            text = await resp.text()
                            if _WAF_BLOCK_MARKER in text:
                                raise WafBlockedError(url)
                            return text
                        data = await resp.read()
                        if _WAF_BLOCK_MARKER.encode() in data:
                            raise WafBlockedError(url)
                        return data
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_exc = exc
            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    async def get_text(self, url: str) -> str:
        """GET the URL and return the decoded text body."""
        result = await self._fetch(url, as_text=True)
        assert isinstance(result, str)
        return result

    async def get_bytes(self, url: str) -> bytes:
        """GET the URL and return the raw bytes body."""
        result = await self._fetch(url, as_text=False)
        assert isinstance(result, bytes)
        return result
