"""Enumerate BK6 proceeding URLs from the laufende and abgeschlossene index surfaces."""

from __future__ import annotations

from bnetza_bk6_scraper.fetch import Fetcher
from bnetza_bk6_scraper.parse import parse_index_page

_BASE = "https://www.bundesnetzagentur.de"
LAUFENDE_URL = f"{_BASE}/DE/Beschlusskammern/BK06/BK6_11_LV/BK6_LV.html"
ABGESCHLOSSENE_URL = f"{_BASE}/DE/Beschlusskammern/BK06/BK6_21_AV/BK6_AV.html"


async def discover_proceeding_urls(fetcher: Fetcher) -> list[str]:
    """Return the de-duplicated set of proceeding page URLs across both index surfaces."""
    collected: list[str] = []
    for index_url in (LAUFENDE_URL, ABGESCHLOSSENE_URL):
        html = await fetcher.get_text(index_url)
        collected += parse_index_page(html, base_url=index_url)
    return list(dict.fromkeys(collected))
