"""Integration test for the mirror orchestrator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

from bnetza_bk6_scraper import discovery
from bnetza_bk6_scraper.scraper import BnetzaBk6Scraper

LV = discovery.LAUFENDE_URL
AV = discovery.ABGESCHLOSSENE_URL
PROC_URL = (
    "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
    "BK6-23-241/BK6-23-241_konsultation.html"
)
# The fixture's PDF href resolves (via <base href="/">) to this absolute URL,
# including the query string, which aioresponses matches on by default.
PDF_URL = (
    "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
    "BK6-23-241/BK6-23-241_konsultationsdokument.pdf?__blob=publicationFile&v=3"
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_mirror_writes_expected_tree(tmp_path: Path) -> None:
    proc_html = (FIXTURES / "proceeding_BK6-23-241_konsultation.html").read_text(
        encoding="utf-8"
    )
    # a minimal laufende index that links exactly one proceeding; empty abgeschlossene
    lv_html = (
        f'<html><body><a href="{PROC_URL}">BK6-23-241</a></body></html>'
    )
    with aioresponses() as mocked:
        mocked.get(LV, status=200, body=lv_html)
        mocked.get(AV, status=200, body="<html><body></body></html>")
        mocked.get(PROC_URL, status=200, body=proc_html)
        mocked.get(PDF_URL, status=200, body=b"%PDF-1.7 fake")
        scraper = BnetzaBk6Scraper()
        await scraper.mirror(tmp_path)

    folder = tmp_path / "2023" / "BK6-23-241"
    assert (folder / "metadata.json").exists()
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert meta["aktenzeichen"] == "BK6-23-241"
    assert (
        folder / "BK6-23-241_konsultationsdokument.pdf"
    ).read_bytes().startswith(b"%PDF")
    assert list(folder.glob("*.html"))  # normalized snapshot written
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert any(entry["aktenzeichen"] == "BK6-23-241" for entry in index)
