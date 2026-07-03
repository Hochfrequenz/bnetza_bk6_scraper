"""Parsing of BNetzA BK6 index and proceeding pages."""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from bnetza_bk6_scraper.models import Document, Proceeding

_AKTENZEICHEN_RE = re.compile(r"(BK6-\d{2}-\d{2,4})")


def _attr_str(tag: Tag, name: str) -> str | None:
    """Return a single string-valued attribute, or None (bs4 attrs are str | list[str])."""
    value = tag.get(name)
    return value if isinstance(value, str) else None


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
    if isinstance(base, Tag):
        href = _attr_str(base, "href")
        if href:
            return urljoin(page_url, href)
    return page_url


def _doc_type_from_filename(filename: str, aktenzeichen: str) -> str:
    stem = filename.rsplit(".", 1)[0]
    prefix = f"{aktenzeichen}_"
    return stem[len(prefix) :] if stem.startswith(prefix) else stem


def phase_from_url(page_url: str) -> str:
    """Phase label from a proceeding URL: '..._konsultation.html?nn=1' -> 'konsultation'.

    Public because the orchestrator reuses it. urlsplit strips any query string first.
    """
    stem = urlsplit(page_url).path.rsplit("/", 1)[-1].removesuffix(".html")
    return stem.split("_", 1)[1] if "_" in stem else stem


def _parse_documents(content: Tag, base: str, aktenzeichen: str) -> list[Document]:
    """Build the list of PDF Documents linked from a proceeding page's content."""
    documents: list[Document] = []
    for anchor in content.select('a[href*=".pdf"]'):
        href_attr = _attr_str(anchor, "href")
        if href_attr is None:
            continue
        href = urljoin(base, href_attr)
        filename = filename_from_pdf_url(href)
        documents.append(
            Document(
                title=anchor.get_text(strip=True) or filename,
                doc_type=_doc_type_from_filename(filename, aktenzeichen),
                source_url=href,
                filename=filename,
            )
        )
    return documents


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

    documents = _parse_documents(content, base, aktenzeichen)
    return Proceeding(
        aktenzeichen=aktenzeichen,
        year=year_from_aktenzeichen(aktenzeichen),
        title=title,
        stand=stand,
        status=status,
        deadline=deadline,
        documents=documents,
    )


def parse_index_page(html: str, base_url: str) -> list[str]:
    """Return absolute URLs of proceeding pages linked from an index page."""
    soup = BeautifulSoup(html, "lxml")
    base = _effective_base(soup, base_url)
    urls: list[str] = []
    for anchor in soup.select("a[href]"):
        href = _attr_str(anchor, "href")
        if href and "/BK6-GZ/" in href and ".html" in href:
            urls.append(urljoin(base, href))
    # dedupe, preserve order
    return list(dict.fromkeys(urls))
