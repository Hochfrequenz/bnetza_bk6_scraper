from datetime import date
from pathlib import Path

from bnetza_bk6_scraper.parse import parse_proceeding_page

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/BK6-23-241/BK6-23-241_konsultation.html"


def test_parse_proceeding_extracts_metadata_and_documents() -> None:
    html = (FIXTURES / "proceeding_BK6-23-241_konsultation.html").read_text(encoding="utf-8")
    parsed = parse_proceeding_page(html, source_url=BASE_URL)

    assert parsed.aktenzeichen == "BK6-23-241"
    assert parsed.year == 2023
    assert "Redispatch 2.0" in parsed.title
    assert parsed.stand == date(2024, 9, 26)
    assert parsed.status == "Konsultation"
    assert parsed.deadline is None or isinstance(parsed.deadline, date)
    assert parsed.documents, "expected at least one PDF"
    assert any("konsultationsdokument" in d.filename for d in parsed.documents)
    assert all(d.source_url.startswith("https://") for d in parsed.documents)
    assert all(d.filename.endswith(".pdf") for d in parsed.documents)
