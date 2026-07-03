"""Parsing of BNetzA BK6 index and proceeding pages."""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from bnetza_bk6_scraper.models import Document, Proceeding

_AKTENZEICHEN_RE = re.compile(r"(BK6-\d{2}-\d{2,4})")


def aktenzeichen_from_url(url: str) -> str:
    """Extract the Aktenzeichen (e.g. 'BK6-23-241') from a proceeding URL."""
    match = _AKTENZEICHEN_RE.search(url)
    if not match:
        raise ValueError(f"no Aktenzeichen found in URL: {url}")
    return match.group(1)


def year_from_aktenzeichen(aktenzeichen: str) -> int:
    """Derive the 4-digit year from the two-digit year in the Aktenzeichen."""
    two_digit = int(aktenzeichen.split("-")[1])
    return 2000 + two_digit if two_digit < 50 else 1900 + two_digit


def filename_from_pdf_url(url: str) -> str:
    """Return the bare filename of a PDF URL."""
    return urlsplit(url).path.rsplit("/", 1)[-1]


def _parse_german_date(text: str) -> date | None:
    match = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
    return datetime.strptime(match.group(0), "%d.%m.%Y").date() if match else None


def _effective_base(soup: BeautifulSoup, page_url: str) -> str:
    """Resolve the page's <base href> (BNetzA uses <base href="/">) against the page URL."""
    base = soup.find("base")
    return urljoin(page_url, base["href"]) if base and base.get("href") else page_url


def _doc_type_from_filename(filename: str, aktenzeichen: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    prefix = f"{aktenzeichen}_"
    return stem[len(prefix):] if stem.startswith(prefix) else stem


def phase_from_url(page_url: str) -> str:
    """Phase label from a proceeding URL: '..._konsultation.html?nn=1' -> 'konsultation'.

    Public because the orchestrator reuses it. urlsplit strips any query string first.
    """
    stem = urlsplit(page_url).path.rsplit("/", 1)[-1].removesuffix(".html")
    return stem.split("_", 1)[1] if "_" in stem else stem


def parse_proceeding_page(html: str, source_url: str) -> Proceeding:
    """Parse one BK6 proceeding phase page into a Proceeding (single page)."""
    soup = BeautifulSoup(html, "lxml")
    base = _effective_base(soup, source_url)
    aktenzeichen = aktenzeichen_from_url(source_url)
    content = soup.select_one("#content") or soup

    heading = content.find("h2")
    title = re.sub(r"\s+", " ", heading.get_text(" ", strip=True)) if heading else aktenzeichen

    stand = None
    stand_node = content.find(string=re.compile(r"Stand:"))
    if stand_node:
        stand = _parse_german_date(str(stand_node))

    phase = phase_from_url(source_url)
    status = phase.replace("_", " ").capitalize() or None

    deadline = None
    label = content.find(string=re.compile(r"(Frist|Stellungnahme).{0,60}?\d{2}\.\d{2}\.\d{4}"))
    if label:
        deadline = _parse_german_date(str(label))

    documents: list[Document] = []
    for anchor in content.select('a[href*=".pdf"]'):
        href = urljoin(base, anchor["href"])
        filename = filename_from_pdf_url(href)
        documents.append(Document(
            title=anchor.get_text(strip=True) or filename,
            doc_type=_doc_type_from_filename(filename, aktenzeichen),
            source_url=href,
            filename=filename,
        ))
    return Proceeding(
        aktenzeichen=aktenzeichen,
        year=year_from_aktenzeichen(aktenzeichen),
        title=title,
        stand=stand,
        status=status,
        deadline=deadline,
        documents=documents,
    )
