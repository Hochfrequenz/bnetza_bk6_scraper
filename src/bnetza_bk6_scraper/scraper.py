"""Orchestrates discovery, download, and writing of the BK6 mirror."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path

from bnetza_bk6_scraper.discovery import discover_proceeding_urls
from bnetza_bk6_scraper.fetch import Fetcher
from bnetza_bk6_scraper.models import Proceeding, ProceedingPage
from bnetza_bk6_scraper.normalize import normalize_html
from bnetza_bk6_scraper.parse import (
    aktenzeichen_from_url,
    parse_proceeding_page,
    phase_from_url,
    year_from_aktenzeichen,
)

_logger = logging.getLogger(__name__)


class BnetzaBk6Scraper:  # pylint: disable=too-few-public-methods
    """Mirrors BK6 proceedings into a structured directory tree."""

    def __init__(self, concurrency: int = 4) -> None:
        self._concurrency = concurrency

    async def mirror(
        self, target_dir: str | Path, year: int | None = None, min_year: int | None = None
    ) -> list[Proceeding]:
        """Download BK6 proceedings into target_dir.

        ``year`` restricts to a single year; ``min_year`` skips proceedings older than that
        year (filtered during discovery, so old proceedings are never downloaded).
        """
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        proceedings: list[Proceeding] = []

        async with Fetcher(concurrency=self._concurrency) as fetcher:
            selected = self._select_proceedings(await discover_proceeding_urls(fetcher), year, min_year)
            attempted = len(selected)

            # Run the selected proceedings concurrently; the Fetcher's semaphore
            # bounds the actual HTTP concurrency, so --concurrency takes effect.
            results = await asyncio.gather(
                *(
                    self._safe_mirror_proceeding(fetcher, aktenzeichen, page_urls, target)
                    for aktenzeichen, page_urls in selected
                )
            )
            proceedings = [p for p in results if p is not None]

        self._write_index(target, proceedings)
        doc_count = sum(len(p.documents) for p in proceedings)
        failures = attempted - len(proceedings)
        _logger.info(
            "run summary: %d proceedings, %d documents written, %d failures",
            len(proceedings),
            doc_count,
            failures,
        )
        return proceedings

    @staticmethod
    def _select_proceedings(urls: list[str], year: int | None, min_year: int | None) -> list[tuple[str, list[str]]]:
        """Group discovered URLs by Aktenzeichen and apply the year / min_year filters."""
        by_az: dict[str, list[str]] = defaultdict(list)
        for url in urls:
            try:
                aktenzeichen = aktenzeichen_from_url(url)
            except ValueError:
                _logger.warning("skipping URL without Aktenzeichen: %s", url)
                continue
            by_az[aktenzeichen].append(url)
        return [
            (aktenzeichen, page_urls)
            for aktenzeichen, page_urls in by_az.items()
            if (year is None or aktenzeichen.startswith(f"BK6-{year % 100:02d}-"))
            and (min_year is None or year_from_aktenzeichen(aktenzeichen) >= min_year)
        ]

    async def _safe_mirror_proceeding(
        self,
        fetcher: Fetcher,
        aktenzeichen: str,
        page_urls: list[str],
        target: Path,
    ) -> Proceeding | None:
        """Mirror one proceeding, logging and swallowing failures so the run continues."""
        try:
            return await self._mirror_proceeding(fetcher, aktenzeichen, page_urls, target)
        except Exception:  # pylint: disable=broad-except
            _logger.warning("failed to mirror %s", aktenzeichen, exc_info=True)
            return None

    async def _mirror_proceeding(
        self,
        fetcher: Fetcher,
        aktenzeichen: str,
        page_urls: list[str],
        target: Path,
    ) -> Proceeding:
        """Fetch, parse, and persist all phase pages and documents of one proceeding."""
        merged: Proceeding | None = None
        pages: list[ProceedingPage] = []
        for url in page_urls:
            html = await fetcher.get_text(url)
            parsed = parse_proceeding_page(html, source_url=url)
            phase = phase_from_url(url)
            pages.append(ProceedingPage(phase=phase, source_url=url))
            folder = target / str(parsed.year) / aktenzeichen
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{aktenzeichen}_{phase}.html").write_text(normalize_html(html), encoding="utf-8")
            if merged is None:
                merged = parsed
            else:
                seen = {d.filename for d in merged.documents}
                merged.documents += [d for d in parsed.documents if d.filename not in seen]
        assert merged is not None
        merged.pages = pages

        folder = target / str(merged.year) / aktenzeichen
        for doc in merged.documents:
            try:
                data = await fetcher.get_bytes(doc.source_url)
                (folder / doc.filename).write_bytes(data)
            except Exception:  # pylint: disable=broad-except
                _logger.warning("failed to download %s", doc.source_url, exc_info=True)
                continue
        # pydantic serializes straight to JSON (dates as ISO strings, non-ASCII preserved),
        # so there's no need to round-trip through model_dump() + json.dumps().
        (folder / "metadata.json").write_text(merged.model_dump_json(indent=2), encoding="utf-8")
        return merged

    @staticmethod
    def _write_index(target: Path, proceedings: list[Proceeding]) -> None:
        """Write the top-level index.json summarizing all mirrored proceedings."""
        index = [
            {
                "aktenzeichen": p.aktenzeichen,
                "year": p.year,
                "title": p.title,
                "status": p.status,
                "stand": p.stand.isoformat() if p.stand else None,
                "path": f"{p.year}/{p.aktenzeichen}",
            }
            for p in sorted(proceedings, key=lambda p: p.aktenzeichen)
        ]
        (target / "index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
