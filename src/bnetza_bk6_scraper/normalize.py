"""Normalize BNetzA HTML pages into stable snapshots for clean git diffs."""

from __future__ import annotations

from bs4 import BeautifulSoup

_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "noscript")
_MAIN_SELECTORS = ("main", "#content", ".content", "#main-content")


def normalize_html(html: str) -> str:
    """Return the main content of a BNetzA page with chrome and scripts removed."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    main = None
    for selector in _MAIN_SELECTORS:
        main = soup.select_one(selector)
        if main is not None:
            break
    node = main if main is not None else (soup.body or soup)
    return node.prettify()
