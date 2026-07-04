"""Orchestrates discovery, download, and writing of the BK6 mirror."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from bnetza_bk6_scraper.discovery import crawl_candidates, discover_proceeding_urls
from bnetza_bk6_scraper.fetch import Fetcher
from bnetza_bk6_scraper.models import CandidateDocument, Proceeding, ProceedingPage
from bnetza_bk6_scraper.normalize import normalize_html
from bnetza_bk6_scraper.parse import (
    aktenzeichen_from_url,
    parse_proceeding_page,
    phase_from_url,
    year_from_aktenzeichen,
)

_logger = logging.getLogger(__name__)


def _relative_path_for(candidate: CandidateDocument) -> Path:
    """Mirror-tree path for a kept candidate.

    Aktenzeichen docs go under ``<year>/<aktenzeichen>/`` (the existing convention). Docs
    without an Aktenzeichen go under ``_other/<path-after-/BK06/>/`` so the layout is a pure
    function of the source URL and hardcodes no topic names."""
    if candidate.aktenzeichen is not None:
        year = year_from_aktenzeichen(candidate.aktenzeichen)
        return Path(str(year)) / candidate.aktenzeichen / candidate.filename
    path = urlsplit(candidate.source_url).path
    marker = "/BK06/"
    tail = path.split(marker, 1)[1] if marker in path else path.lstrip("/")
    # tail includes the filename; rebuild as directory parts + filename
    parts = [p for p in tail.split("/") if p]
    return Path("_other", *parts)


class BnetzaBk6Scraper:
    """Mirrors BK6 proceedings into a structured directory tree."""

    def __init__(
        self, concurrency: int = 4, max_retries: int = 3, backoff_seconds: float = 1.0
    ) -> None:
        self._concurrency = concurrency
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds

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

        async with Fetcher(
            concurrency=self._concurrency,
            max_retries=self._max_retries,
            backoff_seconds=self._backoff_seconds,
        ) as fetcher:
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

    async def mirror_seeds(
        self,
        target_dir: str | Path,
        seeds: list[str],
        keep: list[Callable[[CandidateDocument], bool]],
        max_depth: int = 1,
        url_prefixes: list[str] | None = None,
    ) -> list[CandidateDocument]:
        """Crawl ``seeds`` and download every discovered document accepted by any predicate.

        ``keep`` predicates combine with OR semantics: a candidate is downloaded iff at least
        one predicate returns True. An empty ``keep`` keeps nothing. Aktenzeichen docs are
        written under ``<year>/<aktenzeichen>/``; others under ``_other/…`` (see
        :func:`_relative_path_for`). A root ``manifest.json`` lists the kept documents.
        """
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        async with Fetcher(
            concurrency=self._concurrency,
            max_retries=self._max_retries,
            backoff_seconds=self._backoff_seconds,
        ) as fetcher:
            candidates = await crawl_candidates(fetcher, seeds, max_depth, url_prefixes)
            kept = [c for c in candidates if any(pred(c) for pred in keep)]
            # Download concurrently; the Fetcher's semaphore bounds the actual HTTP
            # concurrency, mirroring the fan-out the full-index mirror() path uses.
            await asyncio.gather(
                *(self._safe_download_candidate(fetcher, cand, target) for cand in kept)
            )

        self._write_manifest(target, kept)
        _logger.info(
            "seed run summary: %d candidates, %d kept, %d seeds",
            len(candidates),
            len(kept),
            len(seeds),
        )
        return kept

    @staticmethod
    async def _safe_download_candidate(
        fetcher: Fetcher, candidate: CandidateDocument, target: Path
    ) -> None:
        """Download one kept candidate and write it, logging and swallowing failures so the
        run continues (matches the per-document behavior of the full-index mirror)."""
        dest = target / _relative_path_for(candidate)
        try:
            data = await fetcher.get_bytes(candidate.source_url)
        except Exception:  # pylint: disable=broad-except
            _logger.warning("failed to download %s", candidate.source_url, exc_info=True)
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    @staticmethod
    def _write_manifest(target: Path, kept: list[CandidateDocument]) -> None:
        """Write manifest.json summarizing the kept documents and where they were written."""
        manifest = [
            {
                "filename": c.filename,
                "title": c.title,
                "aktenzeichen": c.aktenzeichen,
                "doc_type": c.doc_type,
                "source_url": c.source_url,
                "found_on": c.found_on,
                "path": str(_relative_path_for(c)).replace("\\", "/"),
            }
            for c in sorted(kept, key=lambda c: str(_relative_path_for(c)))
        ]
        (target / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

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
