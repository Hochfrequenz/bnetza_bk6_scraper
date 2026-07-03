import asyncio

import pytest
from aioresponses import aioresponses

from bnetza_bk6_scraper.fetch import _HEADERS, Fetcher


@pytest.mark.asyncio
async def test_fetch_text_returns_body() -> None:
    url = "https://www.bundesnetzagentur.de/x.html"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body="<html>ok</html>")
        async with Fetcher(concurrency=2) as fetcher:
            body = await fetcher.get_text(url)
    assert body == "<html>ok</html>"


@pytest.mark.asyncio
async def test_fetch_bytes_returns_content() -> None:
    url = "https://www.bundesnetzagentur.de/x.pdf"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=b"%PDF-1.7")
        async with Fetcher() as fetcher:
            data = await fetcher.get_bytes(url)
    assert data.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_fetch_retries_on_transient_error() -> None:
    url = "https://www.bundesnetzagentur.de/flaky.html"
    with aioresponses() as mocked:
        mocked.get(url, status=503)
        mocked.get(url, status=200, body="recovered")
        async with Fetcher(max_retries=2, backoff_seconds=0) as fetcher:
            body = await fetcher.get_text(url)
    assert body == "recovered"


@pytest.mark.asyncio
async def test_fetch_retries_on_waf_block_page() -> None:
    url = "https://www.bundesnetzagentur.de/blocked.html"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body="... The requested URL was rejected ...")
        mocked.get(url, status=200, body="real content")
        async with Fetcher(max_retries=2, backoff_seconds=0) as fetcher:
            body = await fetcher.get_text(url)
    assert body == "real content"


@pytest.mark.asyncio
async def test_get_bytes_retries_on_waf_block_page() -> None:
    url = "https://www.bundesnetzagentur.de/blocked.pdf"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=b"... The requested URL was rejected ...")
        mocked.get(url, status=200, body=b"%PDF-1.7")
        async with Fetcher(max_retries=2, backoff_seconds=0) as fetcher:
            data = await fetcher.get_bytes(url)
    assert data.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_fetch_retries_on_timeout() -> None:
    url = "https://www.bundesnetzagentur.de/slow.html"
    with aioresponses() as mocked:
        mocked.get(url, exception=asyncio.TimeoutError())
        mocked.get(url, status=200, body="ok")
        async with Fetcher(max_retries=2, backoff_seconds=0) as fetcher:
            body = await fetcher.get_text(url)
    assert body == "ok"


def test_browser_user_agent_configured() -> None:
    assert "Mozilla/5.0" in _HEADERS["User-Agent"]
