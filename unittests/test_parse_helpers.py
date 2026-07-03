import pytest

from bnetza_bk6_scraper.parse import aktenzeichen_from_url, filename_from_pdf_url, year_from_aktenzeichen


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/"
            "BK6-23-241/BK6-23-241_konsultation.html",
            "BK6-23-241",
        ),
        ("/DE/Beschlusskammern/1_GZ/BK6-GZ/2020/BK6-20-061/BK6-20-061_festlegungsverfahren.html", "BK6-20-061"),
    ],
)
def test_aktenzeichen_from_url(url: str, expected: str) -> None:
    assert aktenzeichen_from_url(url) == expected


@pytest.mark.parametrize("az,expected", [("BK6-23-241", 2023), ("BK6-06-001", 2006)])
def test_year_from_aktenzeichen(az: str, expected: int) -> None:
    assert year_from_aktenzeichen(az) == expected


def test_filename_from_pdf_url() -> None:
    url = "/DE/.../BK6-23-241/BK6-23-241_konsultationsdokument.pdf"
    assert filename_from_pdf_url(url) == "BK6-23-241_konsultationsdokument.pdf"


def test_aktenzeichen_from_url_raises_when_absent() -> None:
    with pytest.raises(ValueError):
        aktenzeichen_from_url("https://www.bundesnetzagentur.de/DE/no-aktenzeichen-here.html")


def test_aktenzeichen_from_url_raises_on_conflicting_occurrences() -> None:
    # two *different* Aktenzeichen in one URL is ambiguous -> raise rather than guess
    url = "/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/BK6-23-241/BK6-24-999_x.html"
    with pytest.raises(ValueError):
        aktenzeichen_from_url(url)


def test_year_from_aktenzeichen_raises_on_invalid() -> None:
    with pytest.raises(ValueError):
        year_from_aktenzeichen("not-an-aktenzeichen")
