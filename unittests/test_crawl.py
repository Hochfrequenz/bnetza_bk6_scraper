import pytest
from aioresponses import aioresponses

from bnetza_bk6_scraper.discovery import crawl_candidates
from bnetza_bk6_scraper.fetch import Fetcher

BASE = "https://www.bundesnetzagentur.de"
SEED = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/gpke_node.html"
SUB = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/detail.html"
OFFSITE = "https://example.com/other.html"

SEED_HTML = (
    "<html><head><base href='/'/></head><body>"
    "<a href='/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/BK6-24-174/Beschluss/"
    "BK6-24-174_GPKE_Teil1_Lesefassung.pdf'>GPKE Teil 1</a>"
    "<a href='/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/detail.html'>Detail</a>"
    "<a href='https://example.com/other.html'>offsite</a>"
    "</body></html>"
)
SUB_HTML = (
    "<html><head><base href='/'/></head><body>"
    "<a href='/DE/Beschlusskammern/1_GZ/BK6-GZ/2022/BK6-22-024/Beschluss/"
    "Anlage1d_GPKE_Teil4.pdf'>GPKE Teil 4</a>"
    "</body></html>"
)


@pytest.mark.asyncio
async def test_depth_zero_only_reads_seed() -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        async with Fetcher() as fetcher:
            cands = await crawl_candidates(fetcher, [SEED], max_depth=0)
    names = {c.filename for c in cands}
    assert names == {"BK6-24-174_GPKE_Teil1_Lesefassung.pdf"}  # sub-page not followed


@pytest.mark.asyncio
async def test_depth_one_follows_same_prefix_subpage() -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        mocked.get(SUB, status=200, body=SUB_HTML)
        # OFFSITE intentionally NOT mocked: must never be fetched (different host/prefix)
        async with Fetcher() as fetcher:
            cands = await crawl_candidates(fetcher, [SEED], max_depth=1)
    names = {c.filename for c in cands}
    assert names == {"BK6-24-174_GPKE_Teil1_Lesefassung.pdf", "Anlage1d_GPKE_Teil4.pdf"}


@pytest.mark.asyncio
async def test_crawl_dedupes_and_survives_fetch_error() -> None:
    # SUB_HTML here links back to SEED (cycle) so the visited-guard is exercised; SEED is
    # fetched once; a broken sub-page is skipped without aborting the crawl.
    seed_html = SEED_HTML + f"<a href='{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/broken.html'>b</a>"
    sub_html_with_backlink = SUB_HTML.replace("</body>", f"<a href='{SEED}'>back</a></body>")
    broken = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/broken.html"
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=seed_html)
        mocked.get(SUB, status=200, body=sub_html_with_backlink)
        mocked.get(broken, status=500)
        mocked.get(broken, status=500)
        mocked.get(broken, status=500)
        mocked.get(broken, status=500)
        async with Fetcher(max_retries=0) as fetcher:
            cands = await crawl_candidates(fetcher, [SEED], max_depth=1)
    # both good PDFs present exactly once despite the broken sub-page
    names = sorted(c.filename for c in cands)
    assert names == ["Anlage1d_GPKE_Teil4.pdf", "BK6-24-174_GPKE_Teil1_Lesefassung.pdf"]
