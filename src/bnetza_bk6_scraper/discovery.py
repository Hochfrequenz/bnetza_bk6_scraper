"""Enumerate BK6 proceeding URLs from the laufende and abgeschlossene index surfaces."""

from __future__ import annotations

import logging
from collections import deque
from urllib.parse import urlsplit

from bnetza_bk6_scraper.fetch import Fetcher
from bnetza_bk6_scraper.models import CandidateDocument
from bnetza_bk6_scraper.parse import (
    parse_candidate_documents,
    parse_followable_links,
    parse_index_page,
)

_logger = logging.getLogger(__name__)

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


def _default_prefix(url: str) -> str:
    """The seed's own directory: the URL up to and including its last '/'."""
    return url.rsplit("/", 1)[0] + "/"


async def crawl_candidates(
    fetcher: Fetcher,
    seeds: list[str],
    max_depth: int = 1,
    url_prefixes: list[str] | None = None,
) -> list[CandidateDocument]:
    """Breadth-first crawl from ``seeds`` collecting every PDF link as a CandidateDocument.

    Follows same-host HTML sub-links whose URL starts with one of ``url_prefixes`` (default:
    each seed's own directory) up to ``max_depth`` levels below the seeds. Pages are fetched
    at most once; candidates are de-duplicated by ``source_url``. A page that fails to fetch
    is logged and skipped so the crawl continues.
    """
    prefixes = url_prefixes if url_prefixes is not None else [_default_prefix(s) for s in seeds]
    visited: set[str] = set()
    candidates: dict[str, CandidateDocument] = {}
    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)

    while queue:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            html = await fetcher.get_text(url)
        except Exception:  # pylint: disable=broad-except
            _logger.warning("failed to crawl %s", url, exc_info=True)
            continue
        for cand in parse_candidate_documents(html, page_url=url):
            candidates.setdefault(cand.source_url, cand)
        if depth < max_depth:
            for link in parse_followable_links(html, page_url=url):
                if link in visited:
                    continue
                same_host = urlsplit(link).netloc == urlsplit(url).netloc
                if same_host and any(link.startswith(p) for p in prefixes):
                    queue.append((link, depth + 1))
    return list(candidates.values())
