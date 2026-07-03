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


@pytest.mark.parametrize(
    "url,expected",
    [
        # filename references a different (amended/related) Aktenzeichen than its directory:
        # we key on the directory (the proceeding the document is filed under), not the filename.
        (
            "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2018/"
            "BK6-18-004/BK6-18-006-F6_beschluss_vom_30_01_2019.html?nn=861698",
            "BK6-18-004",
        ),
        (
            "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2019/"
            "BK6-19-601/BK6-15-045_Ae_Beschluss.html?nn=861698",
            "BK6-19-601",
        ),
        (
            "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/_bis_2010/2010/"
            "BK6-10-097bis-099/BK6-10-099_Beschluss.html?nn=861698",
            "BK6-10-097",
        ),
        # nested sub-case directory groups under its parent proceeding
        (
            "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/"
            "BK6-24-210/BK6-24-210-1/BK6-24-210-1_Konsultation.html",
            "BK6-24-210",
        ),
    ],
)
def test_aktenzeichen_from_url_keys_on_directory_not_filename(url: str, expected: str) -> None:
    assert aktenzeichen_from_url(url) == expected


def test_year_from_aktenzeichen_raises_on_invalid() -> None:
    with pytest.raises(ValueError):
        year_from_aktenzeichen("not-an-aktenzeichen")
