from pathlib import Path

import pytest
from aioresponses import aioresponses

from bnetza_bk6_scraper import discovery
from bnetza_bk6_scraper.discovery import discover_proceeding_urls
from bnetza_bk6_scraper.fetch import Fetcher

FIXTURES = Path(__file__).parent / "fixtures"
LV = discovery.LAUFENDE_URL
AV = discovery.ABGESCHLOSSENE_URL


@pytest.mark.asyncio
async def test_discover_collects_urls_from_both_surfaces() -> None:
    lv_html = (FIXTURES / "laufende_verfahren.html").read_text(encoding="utf-8")
    av_html = (FIXTURES / "abgeschlossene_verfahren.html").read_text(encoding="utf-8")
    with aioresponses() as mocked:
        mocked.get(LV, status=200, body=lv_html)
        mocked.get(AV, status=200, body=av_html)
        async with Fetcher() as fetcher:
            urls = await discover_proceeding_urls(fetcher)
    assert len(urls) > 100
    assert all("/BK6-GZ/" in u for u in urls)
    assert len(urls) == len(set(urls))
