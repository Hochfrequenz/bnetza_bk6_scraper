from pathlib import Path
from bnetza_bk6_scraper.parse import parse_index_page

FIXTURES = Path(__file__).parent / "fixtures"
LV = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/BK06/BK6_11_LV/BK6_LV.html"
AV = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/BK06/BK6_21_AV/BK6_AV.html"


def test_parse_laufende_index_returns_absolute_proceeding_urls() -> None:
    html = (FIXTURES / "laufende_verfahren.html").read_text(encoding="utf-8")
    urls = parse_index_page(html, base_url=LV)
    assert urls, "expected at least one proceeding link"
    assert all(u.startswith("https://www.bundesnetzagentur.de/DE/") for u in urls)
    assert all("/BK6-GZ/" in u for u in urls)


def test_parse_abgeschlossene_index_lists_many() -> None:
    html = (FIXTURES / "abgeschlossene_verfahren.html").read_text(encoding="utf-8")
    urls = parse_index_page(html, base_url=AV)
    assert len(urls) > 100
