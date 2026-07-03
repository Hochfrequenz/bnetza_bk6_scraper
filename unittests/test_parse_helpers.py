import pytest
from bnetza_bk6_scraper.parse import aktenzeichen_from_url, year_from_aktenzeichen, filename_from_pdf_url


@pytest.mark.parametrize("url,expected", [
    ("https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/BK6-23-241/BK6-23-241_konsultation.html", "BK6-23-241"),
    ("/DE/Beschlusskammern/1_GZ/BK6-GZ/2020/BK6-20-061/BK6-20-061_festlegungsverfahren.html", "BK6-20-061"),
])
def test_aktenzeichen_from_url(url, expected):
    assert aktenzeichen_from_url(url) == expected


@pytest.mark.parametrize("az,expected", [("BK6-23-241", 2023), ("BK6-06-001", 2006)])
def test_year_from_aktenzeichen(az, expected):
    assert year_from_aktenzeichen(az) == expected


def test_filename_from_pdf_url():
    url = "/DE/.../BK6-23-241/BK6-23-241_konsultationsdokument.pdf"
    assert filename_from_pdf_url(url) == "BK6-23-241_konsultationsdokument.pdf"
