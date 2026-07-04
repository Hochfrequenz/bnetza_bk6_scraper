"""Parsing of BNetzA BK6 index and proceeding pages."""

from __future__ import annotations

import re
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from bnetza_bk6_scraper.models import CandidateDocument, Document, Proceeding

# Named components make the shape self-documenting and let callers pull out the
# two-digit year without re-splitting the string: BK6-<yy>-<sequence>, e.g. BK6-23-241.
_AKTENZEICHEN_RE = re.compile(r"(?P<aktenzeichen>BK6-(?P<yy>\d{2})-(?P<sequence>\d{2,4}))")


def _attr_str(tag: Tag, name: str) -> str | None:
    """Return a single string-valued attribute, or None (bs4 attrs are str | list[str])."""
    value = tag.get(name)
    return value if isinstance(value, str) else None


def aktenzeichen_from_url(url: str) -> str:
    """Extract the proceeding's Aktenzeichen (e.g. 'BK6-23-241') from a BK6 URL.

    A BK6 document lives under a proceeding *directory* named by its Aktenzeichen, e.g.
    ``.../BK6-GZ/2023/BK6-23-241/BK6-23-241_konsultation.html``. The document *filename* may
    legitimately reference a *different* (sub-, amended or related) Aktenzeichen, e.g.
    ``.../2019/BK6-19-601/BK6-15-045_Ae_Beschluss.html`` or
    ``.../2018/BK6-18-004/BK6-18-006-F6_beschluss...html``. We therefore key on the
    **directory** — the first path segment that carries an Aktenzeichen — not the filename,
    so such documents are grouped under their proceeding instead of being dropped.
    """
    for segment in urlsplit(url).path.split("/"):
        match = _AKTENZEICHEN_RE.search(segment)
        if match:
            return match.group("aktenzeichen")
    raise ValueError(f"no Aktenzeichen found in URL: {url}")


def year_from_aktenzeichen(aktenzeichen: str) -> int:
    """Derive the 4-digit year from the two-digit year embedded in the Aktenzeichen."""
    match = _AKTENZEICHEN_RE.search(aktenzeichen)
    if not match:
        raise ValueError(f"not a valid Aktenzeichen: {aktenzeichen}")
    two_digit = int(match.group("yy"))
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


def parse_candidate_documents(html: str, page_url: str) -> list[CandidateDocument]:
    """Extract every PDF link on a page as a CandidateDocument, with source context.

    Unlike :func:`_parse_documents`, this works on any page (topic pages, notice pages),
    so the Aktenzeichen may be absent — in which case ``aktenzeichen``/``doc_type`` are None.
    """
    soup = BeautifulSoup(html, "lxml")
    base = _effective_base(soup, page_url)
    candidates: list[CandidateDocument] = []
    seen: set[str] = set()
    for anchor in soup.select('a[href*=".pdf"]'):
        href_attr = _attr_str(anchor, "href")
        if href_attr is None:
            continue
        href = urljoin(base, href_attr)
        if href in seen:
            continue
        seen.add(href)
        filename = filename_from_pdf_url(href)
        try:
            aktenzeichen: str | None = aktenzeichen_from_url(href)
        except ValueError:
            aktenzeichen = None
        doc_type = _doc_type_from_filename(filename, aktenzeichen) if aktenzeichen else None
        candidates.append(
            CandidateDocument(
                source_url=href,
                filename=filename,
                title=anchor.get_text(strip=True) or filename,
                found_on=page_url,
                aktenzeichen=aktenzeichen,
                doc_type=doc_type,
            )
        )
    return candidates


def parse_followable_links(html: str, page_url: str) -> list[str]:
    """Return de-duplicated absolute URLs of non-PDF HTML anchors on the page.

    Used by the bounded crawler to enqueue sub-pages. PDF links are excluded (they are
    handled by :func:`parse_candidate_documents`)."""
    soup = BeautifulSoup(html, "lxml")
    base = _effective_base(soup, page_url)
    links: list[str] = []
    for anchor in soup.select("a[href]"):
        href = _attr_str(anchor, "href")
        if not href or ".pdf" in href.lower():
            continue
        links.append(urljoin(base, href))
    return list(dict.fromkeys(links))


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
    # Only trust a date that sits close after a "Frist"/"Stellungnahme" label. The {0,60}
    # window (a heuristic, ~one clause of German prose, non-greedy) keeps us on the date that
    # belongs to the label and avoids latching onto an unrelated date elsewhere in the text;
    # it is deliberately generous enough to span short wording like "Frist zur Stellungnahme: ".
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
