import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

from bnetza_bk6_scraper.models import CandidateDocument
from bnetza_bk6_scraper.scraper import BnetzaBk6Scraper

BASE = "https://www.bundesnetzagentur.de"
SEED = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/gpke_node.html"
GPKE_PDF = f"{BASE}/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/BK6-24-174/Beschluss/" "BK6-24-174_GPKE_Teil1_Lesefassung.pdf"
GPKE_AENDERUNG = (
    f"{BASE}/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/BK6-24-174/Beschluss/" "BK6-24-174_GPKE_Teil1_Aenderung.pdf"
)
PID_PDF = (
    f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/835_mitteilungen_datenformate/"
    "Mitteilung_48/Anlagen/PID_3_2.pdf"
)
SEED_HTML = (
    "<html><head><base href='/'/></head><body>"
    f"<a href='{GPKE_PDF}'>GPKE Teil 1 (Lesefassung)</a>"
    f"<a href='{GPKE_AENDERUNG}'>GPKE Teil 1 (Änderungsmodus)</a>"
    f"<a href='{PID_PDF}'>Anwendungsübersicht der Prüfidentifikatoren</a>"
    "</body></html>"
)


def _keep_lesefassung(c: CandidateDocument) -> bool:
    name = c.filename.lower()
    return "gpke_" in name and "lesefassung" in name and "aenderung" not in name


def _keep_pid(c: CandidateDocument) -> bool:
    return c.filename.lower().startswith("pid_")


@pytest.mark.asyncio
async def test_mirror_seeds_writes_both_layout_branches(tmp_path: Path) -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        mocked.get(GPKE_PDF, status=200, body=b"%PDF-1.7 gpke")
        mocked.get(PID_PDF, status=200, body=b"%PDF-1.7 pid")
        # GPKE_AENDERUNG intentionally NOT mocked: no predicate keeps it, so it is never fetched.
        scraper = BnetzaBk6Scraper()
        kept = await scraper.mirror_seeds(tmp_path, seeds=[SEED], keep=[_keep_lesefassung, _keep_pid], max_depth=0)

    assert {c.filename for c in kept} == {
        "BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        "PID_3_2.pdf",
    }
    # Aktenzeichen branch
    gpke_path = tmp_path / "2024" / "BK6-24-174" / "BK6-24-174_GPKE_Teil1_Lesefassung.pdf"
    assert gpke_path.read_bytes().startswith(b"%PDF")
    # non-Aktenzeichen branch: _other/<path-after-/BK06/>/<filename>
    pid_path = (
        tmp_path
        / "_other"
        / "BK6_83_Zug_Mess"
        / "835_mitteilungen_datenformate"
        / "Mitteilung_48"
        / "Anlagen"
        / "PID_3_2.pdf"
    )
    assert pid_path.read_bytes().startswith(b"%PDF")
    # manifest lists both kept docs
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert {entry["filename"] for entry in manifest} == {
        "BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        "PID_3_2.pdf",
    }


@pytest.mark.asyncio
async def test_mirror_seeds_empty_keep_downloads_nothing(tmp_path: Path) -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        scraper = BnetzaBk6Scraper()
        kept = await scraper.mirror_seeds(tmp_path, seeds=[SEED], keep=[], max_depth=0)
    assert kept == []
    assert not any(tmp_path.rglob("*.pdf"))


@pytest.mark.asyncio
async def test_mirror_seeds_continues_when_one_download_fails(tmp_path: Path) -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        mocked.get(GPKE_PDF, status=404)
        mocked.get(PID_PDF, status=200, body=b"%PDF-1.7 pid")
        # backoff_seconds=0 so the retried 404 fails fast instead of sleeping ~6s
        scraper = BnetzaBk6Scraper(backoff_seconds=0.0)
        kept = await scraper.mirror_seeds(tmp_path, seeds=[SEED], keep=[_keep_lesefassung, _keep_pid], max_depth=0)
    # both are "kept" (selected), but only the one that downloaded lands on disk
    assert {c.filename for c in kept} == {
        "BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        "PID_3_2.pdf",
    }
    assert not (tmp_path / "2024" / "BK6-24-174" / "BK6-24-174_GPKE_Teil1_Lesefassung.pdf").exists()
    assert (
        tmp_path
        / "_other"
        / "BK6_83_Zug_Mess"
        / "835_mitteilungen_datenformate"
        / "Mitteilung_48"
        / "Anlagen"
        / "PID_3_2.pdf"
    ).exists()
