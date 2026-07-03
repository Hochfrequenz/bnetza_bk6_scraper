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


# A synthetic proceeding page linking two distinct PDFs, an <h2> title and #content.
PROC_TWO_PDFS = (
    "<html><head><base href='/'/></head><body><div id='content'>"
    "<h2>Zwei Dokumente</h2>"
    "<a href='https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/"
    "BK6-GZ/2023/BK6-23-241/BK6-23-241_x.pdf'>Dokument X</a>"
    "<a href='https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/"
    "BK6-GZ/2023/BK6-23-241/BK6-23-241_y.pdf'>Dokument Y</a>"
    "</div></body></html>"
)
PDF_X = (
    "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
    "BK6-23-241/BK6-23-241_x.pdf"
)
PDF_Y = (
    "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
    "BK6-23-241/BK6-23-241_y.pdf"
)


@pytest.mark.asyncio
async def test_mirror_continues_when_one_pdf_fails(tmp_path: Path) -> None:
    lv_html = f'<html><body><a href="{PROC_URL}">BK6-23-241</a></body></html>'
    with aioresponses() as mocked:
        mocked.get(LV, status=200, body=lv_html)
        mocked.get(AV, status=200, body="<html><body></body></html>")
        mocked.get(PROC_URL, status=200, body=PROC_TWO_PDFS)
        mocked.get(PDF_X, status=200, body=b"%PDF-1.7 good")
        mocked.get(PDF_Y, status=404)
        scraper = BnetzaBk6Scraper()
        proceedings = await scraper.mirror(tmp_path)

    # the proceeding is not dropped despite one failed download
    assert any(p.aktenzeichen == "BK6-23-241" for p in proceedings)
    folder = tmp_path / "2023" / "BK6-23-241"
    assert (folder / "metadata.json").exists()
    assert (folder / "BK6-23-241_x.pdf").read_bytes().startswith(b"%PDF")
    assert not (folder / "BK6-23-241_y.pdf").exists()


def _synthetic_proceeding_page(az: str) -> str:
    """A minimal proceeding page with #content, an <h2> title and one .pdf link."""
    pdf = (
        "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
        f"{az}/{az}_dok.pdf"
    )
    return (
        "<html><head><base href='/'/></head><body><div id='content'>"
        f"<h2>Titel {az}</h2>"
        f"<a href='{pdf}'>Dokument</a>"
        "</div></body></html>"
    )


@pytest.mark.asyncio
async def test_mirror_processes_multiple_proceedings(tmp_path: Path) -> None:
    az_one = "BK6-23-001"
    az_two = "BK6-23-002"
    proc_one_url = (
        "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
        f"{az_one}/{az_one}_konsultation.html"
    )
    proc_two_url = (
        "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
        f"{az_two}/{az_two}_konsultation.html"
    )
    pdf_one = (
        "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
        f"{az_one}/{az_one}_dok.pdf"
    )
    pdf_two = (
        "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
        f"{az_two}/{az_two}_dok.pdf"
    )
    lv_html = (
        f'<html><body><a href="{proc_one_url}">{az_one}</a>'
        f'<a href="{proc_two_url}">{az_two}</a></body></html>'
    )
    with aioresponses() as mocked:
        mocked.get(LV, status=200, body=lv_html)
        mocked.get(AV, status=200, body="<html><body></body></html>")
        mocked.get(proc_one_url, status=200, body=_synthetic_proceeding_page(az_one))
        mocked.get(proc_two_url, status=200, body=_synthetic_proceeding_page(az_two))
        mocked.get(pdf_one, status=200, body=b"%PDF-1.7 one")
        mocked.get(pdf_two, status=200, body=b"%PDF-1.7 two")
        scraper = BnetzaBk6Scraper()
        proceedings = await scraper.mirror(tmp_path)

    assert {p.aktenzeichen for p in proceedings} == {az_one, az_two}
    for az in (az_one, az_two):
        assert (tmp_path / "2023" / az / "metadata.json").exists()
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    listed = {entry["aktenzeichen"] for entry in index}
    assert {az_one, az_two} <= listed


@pytest.mark.asyncio
async def test_mirror_skips_index_link_without_aktenzeichen(tmp_path: Path) -> None:
    proc_html = (FIXTURES / "proceeding_BK6-23-241_konsultation.html").read_text(
        encoding="utf-8"
    )
    bad_url = (
        "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
        "overview.html"
    )
    lv_html = (
        f'<html><body><a href="{PROC_URL}">BK6-23-241</a>'
        f'<a href="{bad_url}">Übersicht 2023</a></body></html>'
    )
    with aioresponses() as mocked:
        mocked.get(LV, status=200, body=lv_html)
        mocked.get(AV, status=200, body="<html><body></body></html>")
        mocked.get(PROC_URL, status=200, body=proc_html)
        mocked.get(PDF_URL, status=200, body=b"%PDF-1.7 fake")
        scraper = BnetzaBk6Scraper()
        proceedings = await scraper.mirror(tmp_path)

    assert any(p.aktenzeichen == "BK6-23-241" for p in proceedings)
    assert (tmp_path / "2023" / "BK6-23-241" / "metadata.json").exists()
