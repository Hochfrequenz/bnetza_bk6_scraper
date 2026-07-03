from pathlib import Path

from bnetza_bk6_scraper.normalize import normalize_html

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalize_keeps_content_drops_chrome() -> None:
    html = (FIXTURES / "proceeding_BK6-23-241_konsultation.html").read_text(
        encoding="utf-8"
    )
    out = normalize_html(html)
    assert "Redispatch" in out  # main content kept
    assert "Fortentwicklung" in out  # main content kept
    assert "<script" not in out.lower()  # scripts stripped
    assert "<nav" not in out.lower()  # nav stripped
    # deterministic: normalizing twice yields identical output
    assert normalize_html(html) == out
