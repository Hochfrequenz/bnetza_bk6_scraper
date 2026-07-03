"""Parsing of BNetzA BK6 index and proceeding pages."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

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
