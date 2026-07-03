# BNetzA Beschlusskammer 6 Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pip-installable Python package + Typer CLI that mirrors Bundesnetzagentur Beschlusskammer 6 proceedings (metadata + normalized HTML snapshots + PDFs) into a structured, git-diffable directory tree.

**Architecture:** An async `aiohttp` fetch layer feeds pure BeautifulSoup parsers (index pages → proceeding URLs; proceeding pages → metadata + PDF links). A `discovery` module enumerates proceedings from the two index surfaces; a `BnetzaBk6Scraper.mirror()` orchestrator downloads everything and writes `metadata.json` + normalized HTML + PDFs under `/{year}/{aktenzeichen}/`, plus a top-level `index.json`. Change detection is "dumb" — always download; git detects changes. A Typer CLI wraps `mirror()`.

**Tech Stack:** Python 3.11+, `aiohttp`, `beautifulsoup4`, `lxml`, `typer`, `pydantic`; tests with `pytest` + `aioresponses` + recorded HTML fixtures.

**Spec:** `docs/superpowers/specs/2026-07-03-bnetza-bk6-scraper-design.md`

---

## File Structure

- `src/bnetza_bk6_scraper/__init__.py` — package exports (`BnetzaBk6Scraper`, models)
- `src/bnetza_bk6_scraper/models.py` — `Document`, `Proceeding` pydantic models
- `src/bnetza_bk6_scraper/parse.py` — pure parsing helpers + index/proceeding page parsers
- `src/bnetza_bk6_scraper/normalize.py` — main-content extraction for HTML snapshots
- `src/bnetza_bk6_scraper/fetch.py` — async `aiohttp` client wrapper (retry, throttle)
- `src/bnetza_bk6_scraper/discovery.py` — enumerate proceeding URLs from index surfaces
- `src/bnetza_bk6_scraper/scraper.py` — `BnetzaBk6Scraper.mirror()` orchestrator + file writing
- `src/bnetza_bk6_scraper/cli.py` — Typer CLI
- `unittests/fixtures/` — recorded HTML/PDF samples
- `unittests/test_*.py` — one test module per source module

**Fixture paths (important):** the `coverage` tox env runs with `changedir = unittests`, so
cwd-relative paths like `Path("unittests/fixtures/...")` break there. Every test that reads a
fixture MUST resolve it relative to the test file:

```python
FIXTURES = Path(__file__).parent / "fixtures"
```

and read e.g. `(FIXTURES / "proceeding_BK6-23-241_konsultation.html").read_text(encoding="utf-8")`.
The test snippets below use `Path("unittests/fixtures/...")` for brevity — replace with the
`FIXTURES` form in every test module.

---

## Task 1: Project setup — rename package, dependencies, entry point

**Files:**
- Delete: `src/mypackage/mymodule.py`, `unittests/test_myclass.py`
- Rename: `src/mypackage/` → `src/bnetza_bk6_scraper/` (keep `py.typed`)
- Modify: `src/bnetza_bk6_scraper/__init__.py`
- Modify: `pyproject.toml`
- Modify: `tox.ini`

- [ ] **Step 1: Move the package directory and drop example files**

```bash
git mv src/mypackage src/bnetza_bk6_scraper
git rm src/bnetza_bk6_scraper/mymodule.py unittests/test_myclass.py
```

- [ ] **Step 2: Update `pyproject.toml` metadata, dependencies, and CLI entry point**

Replace the `[project]` name/description/authors/keywords/urls placeholders and add dependencies + script entry point:

```toml
[project]
name = "bnetza_bk6_scraper"
description = "Scrapes documents of Bundesnetzagentur Beschlusskammer 6 into a structured, git-diffable mirror"
license = { text = "MIT" }
authors = [{ name = "Hochfrequenz Unternehmensberatung GmbH", email = "info@hochfrequenz.de" }]
keywords = ["bnetza", "bundesnetzagentur", "beschlusskammer", "energy", "scraper"]
# classifiers unchanged
requires-python = ">=3.11"
dependencies = [
    "aiohttp",
    "beautifulsoup4",
    "lxml",
    "typer",
    "pydantic>=2",
]
dynamic = ["readme", "version"]

[project.scripts]
bnetza-bk6-scraper = "bnetza_bk6_scraper.cli:app"

[project.urls]
Changelog = "https://github.com/Hochfrequenz/bnetza_bk6_scraper/releases"
Homepage = "https://github.com/Hochfrequenz/bnetza_bk6_scraper"
```

Add `aioresponses` to the `tests` optional-dependency group:

```toml
tests = [
    "pytest==9.1.1",
    "aioresponses",
]
```

Update the `[tool.hatch.build.hooks.vcs]` version-file path to `src/bnetza_bk6_scraper/_version.py` (and add that file to `.gitignore` if not covered).

Also add pytest-asyncio config so the async tests (Task 8 onward) run:

```toml
tests = [
    "pytest==9.1.1",
    "pytest-asyncio",
    "aioresponses",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 2b: Update `tox.ini` to reference the renamed package**

The template hardcodes `mypackage` in two envs that `tox` runs (Task 12). Update:
- `[testenv:linting]`: `pylint mypackage` → `pylint bnetza_bk6_scraper`
- `[testenv:type_check]`: `mypy --show-error-codes src/mypackage --strict` → `mypy --show-error-codes src/bnetza_bk6_scraper --strict`

- [ ] **Step 3: Replace `__init__.py` with a placeholder export surface**

```python
"""bnetza_bk6_scraper: mirror Bundesnetzagentur Beschlusskammer 6 documents."""
```

(Real exports added as classes are implemented.)

- [ ] **Step 4: Recreate the dev environment and verify import**

Run: `tox -e dev` then `python -c "import bnetza_bk6_scraper"`
Expected: no import error.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: initialize bnetza_bk6_scraper package from template"
```

---

## Task 2: Data models (`models.py`)

**Files:**
- Create: `src/bnetza_bk6_scraper/models.py`
- Test: `unittests/test_models.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from bnetza_bk6_scraper.models import Document, Proceeding


def test_document_minimal():
    doc = Document(
        title="Konsultationsdokument",
        doc_type="konsultationsdokument",
        source_url="https://www.bundesnetzagentur.de/.../BK6-23-241_konsultationsdokument.pdf",
        filename="BK6-23-241_konsultationsdokument.pdf",
    )
    assert doc.filename.endswith(".pdf")


def test_proceeding_roundtrips_to_json():
    p = Proceeding(
        aktenzeichen="BK6-23-241",
        year=2023,
        title="Fortentwicklung des sog. 'Redispatch 2.0'",
        stand=date(2024, 9, 26),
        status="Konsultation",
        deadline=date(2024, 11, 4),
        pages=[],
        documents=[],
    )
    dumped = p.model_dump(mode="json")
    assert dumped["aktenzeichen"] == "BK6-23-241"
    assert dumped["stand"] == "2024-09-26"
    assert Proceeding.model_validate(dumped) == p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: bnetza_bk6_scraper.models`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Pydantic models describing a BK6 proceeding and its documents."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class Document(BaseModel):
    """A single downloadable document (PDF) belonging to a proceeding."""

    title: str
    doc_type: str
    source_url: str
    filename: str


class ProceedingPage(BaseModel):
    """One phase page (e.g. konsultation, festlegungsverfahren) of a proceeding."""

    phase: str
    source_url: str


class Proceeding(BaseModel):
    """A BK6 proceeding, keyed by Aktenzeichen, aggregating all its phase pages."""

    aktenzeichen: str
    year: int
    title: str
    stand: date | None = None
    status: str | None = None
    deadline: date | None = None
    pages: list[ProceedingPage] = []
    documents: list[Document] = []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `tox -e tests -- unittests/test_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/models.py unittests/test_models.py
git commit -m "feat: add Document and Proceeding models"
```

---

## Task 3: Pure parsing helpers — Aktenzeichen / year / filename derivation (`parse.py`)

Pure functions first (no HTML, trivial to TDD). These lock in the year-derivation and path rules from the spec.

**Files:**
- Create: `src/bnetza_bk6_scraper/parse.py`
- Test: `unittests/test_parse_helpers.py`

- [ ] **Step 1: Write the failing test**

```python
import pytest
from bnetza_bk6_scraper.parse import aktenzeichen_from_url, year_from_aktenzeichen, filename_from_pdf_url


@pytest.mark.parametrize("url,expected", [
    ("https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/BK6-23-241/BK6-23-241_konsultation.html", "BK6-23-241"),
    ("/DE/Beschlusskammern/1_GZ/BK6-GZ/2020/BK6-20-061/BK6-20-061_festlegungsverfahren.html", "BK6-20-061"),
])
def test_aktenzeichen_from_url(url, expected):
    assert aktenzeichen_from_url(url) == expected


@pytest.mark.parametrize("az,expected", [("BK6-23-241", 2023), ("BK6-06-001", 2006), ("BK6-99-001", 1999)])
def test_year_from_aktenzeichen(az, expected):
    assert year_from_aktenzeichen(az) == expected


def test_filename_from_pdf_url():
    url = "/DE/.../BK6-23-241/BK6-23-241_konsultationsdokument.pdf"
    assert filename_from_pdf_url(url) == "BK6-23-241_konsultationsdokument.pdf"
```

Note on `year_from_aktenzeichen`: two-digit year `YY` maps to `2000+YY` when `YY < 50`, else `1900+YY` (BK6 records begin 2006; pivot keeps the helper total). Confirm the pivot against real data during Task 8; adjust the test if BNetzA has no pre-2000 BK6 proceedings (it does not — a fixed `2000+YY` is acceptable, drop the 1999 case if so).

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_parse_helpers.py -v`
Expected: FAIL with import error.

- [ ] **Step 3: Write minimal implementation**

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `tox -e tests -- unittests/test_parse_helpers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/parse.py unittests/test_parse_helpers.py
git commit -m "feat: add Aktenzeichen/year/filename parsing helpers"
```

---

## Task 4: Record HTML fixtures ✅ DONE

**Status: complete** (commit recorded 3 real fixtures + `.gitattributes`). Documented here for reference; no further action.

Real pages are needed before writing HTML parsers. They were saved once; tests run offline against them.

**Files recorded:**
- `unittests/fixtures/laufende_verfahren.html` — ongoing-proceedings index (~13 proceeding links)
- `unittests/fixtures/abgeschlossene_verfahren.html` — completed-proceedings landing page; **lists all 430+ proceedings directly** (no per-year subpages)
- `unittests/fixtures/proceeding_BK6-23-241_konsultation.html` — a proceeding page (Redispatch 2.0)
- `.gitattributes` with `unittests/fixtures/** -text` so fixture bytes are preserved exactly (no CRLF conversion → stable parser tests)

**Key facts learned (encoded into Tasks 5, 6, 8, 9):**
- BNetzA sits behind a **WAF** that returns a **200-status block page** ("The requested URL was rejected") for bot User-Agents. A **browser User-Agent + `Accept`/`Accept-Language` headers** are required (see the `curl` recipe below and Task 8's `_HEADERS`).
- Pages set `<base href="/">` — links resolve against the site root, not the page URL.
- The `<h1>` is the Aktenzeichen; the title is the `<h2>` inside `#content`.
- PDF/proceeding hrefs carry query strings (`?__blob=…`, `?nn=…`) — filter with "contains", not "ends-with".
- The fixtures are valid UTF-8.

The recipe used (browser UA is essential — a bot UA yields the block page):
```bash
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
curl -sSL -A "$UA" -H "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8" \
  -H "Accept-Language: de-DE,de;q=0.9,en;q=0.8" \
  "https://www.bundesnetzagentur.de/DE/Beschlusskammern/BK06/BK6_11_LV/BK6_LV.html" \
  -o unittests/fixtures/laufende_verfahren.html
```

---

## Task 5: Parse a proceeding page — metadata + PDF links (`parse.py`)

**Files:**
- Modify: `src/bnetza_bk6_scraper/parse.py`
- Test: `unittests/test_parse_proceeding.py`

- [ ] **Step 1: Write the failing test**

```python
from datetime import date
from pathlib import Path
from bnetza_bk6_scraper.parse import parse_proceeding_page

FIXTURES = Path(__file__).parent / "fixtures"
BASE_URL = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/BK6-23-241/BK6-23-241_konsultation.html"


def test_parse_proceeding_extracts_metadata_and_documents():
    html = (FIXTURES / "proceeding_BK6-23-241_konsultation.html").read_text(encoding="utf-8")
    parsed = parse_proceeding_page(html, source_url=BASE_URL)

    assert parsed.aktenzeichen == "BK6-23-241"
    assert parsed.year == 2023
    assert "Redispatch 2.0" in parsed.title            # real title lives in <h2> under #content
    assert parsed.stand == date(2024, 9, 26)
    # status is derived from the page phase (reliable); deadline is best-effort (may be None)
    assert parsed.status == "Konsultation"
    assert parsed.deadline is None or isinstance(parsed.deadline, date)
    # the consultation PDF is discovered as an absolute URL — note real hrefs end
    # ".pdf?__blob=publicationFile&v=3", so an `a[href$=".pdf"]` selector would match NOTHING.
    assert parsed.documents, "expected at least one PDF"
    assert any("konsultationsdokument" in d.filename for d in parsed.documents)
    assert all(d.source_url.startswith("https://") for d in parsed.documents)
    assert all(d.filename.endswith(".pdf") for d in parsed.documents)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_parse_proceeding.py -v`
Expected: FAIL (`parse_proceeding_page` undefined).

- [ ] **Step 3: Write minimal implementation**

Add to `parse.py`. The selectors below are **verified against the recorded fixture** — the
DOM facts they encode (confirmed during Task 4):
- BNetzA pages set `<base href="/">`, so links MUST be resolved against `urljoin(page_url, base_href)` (→ site root), NOT against `page_url` directly. Otherwise root-relative hrefs like `DE/...` resolve to broken nested paths.
- The `<h1>` is the **Aktenzeichen**; the real proceeding **title is the `<h2>` inside `#content`**.
- PDF hrefs end with a query string (`....pdf?__blob=publicationFile&v=3`), so use `a[href*=".pdf"]` (contains), never `a[href$=".pdf"]` (ends-with → matches nothing). `filename_from_pdf_url` (Task 3) already strips the query via `urlsplit(...).path`.
- `status` is derived from the page **phase** (the URL filename suffix, e.g. `_konsultation` → "Konsultation") — reliable, unlike scraping a status label from the DOM.
- `deadline` is **best-effort**: the deadline date on this page sits in a bare cell with no adjacent label, so a label-anchored search yields `None` here. That's acceptable — deadline defaults to `None` when not confidently found.

```python
from datetime import date, datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from bnetza_bk6_scraper.models import Document, Proceeding


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

    Public because the orchestrator (scraper.py) reuses it. Uses urlsplit so any query
    string is stripped before deriving the phase.
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
    title = heading.get_text(strip=True) if heading else aktenzeichen

    stand = None
    stand_node = content.find(string=re.compile(r"Stand:"))
    if stand_node:
        stand = _parse_german_date(str(stand_node))

    phase = phase_from_url(source_url)
    status = phase.replace("_", " ").capitalize() or None

    # deadline: best-effort — only trust a date next to a Frist/Stellungnahme label.
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
```

- [ ] **Step 4: Run test; iterate selectors against the fixture until it passes**

Run: `tox -e tests -- unittests/test_parse_proceeding.py -v`
Expected: PASS. If selectors miss, inspect the fixture DOM and adjust.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/parse.py unittests/test_parse_proceeding.py
git commit -m "feat: parse BK6 proceeding page metadata and PDF links"
```

---

## Task 6: Parse index pages → proceeding URLs (`parse.py`)

**Files:**
- Modify: `src/bnetza_bk6_scraper/parse.py`
- Test: `unittests/test_parse_index.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from bnetza_bk6_scraper.parse import parse_index_page

FIXTURES = Path(__file__).parent / "fixtures"
LV = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/BK06/BK6_11_LV/BK6_LV.html"
AV = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/BK06/BK6_21_AV/BK6_AV.html"


def test_parse_laufende_index_returns_absolute_proceeding_urls():
    html = (FIXTURES / "laufende_verfahren.html").read_text(encoding="utf-8")
    urls = parse_index_page(html, base_url=LV)
    assert urls, "expected at least one proceeding link"
    # base-href resolution must yield absolute site URLs, not broken nested paths
    assert all(u.startswith("https://www.bundesnetzagentur.de/DE/") for u in urls)
    assert all("/BK6-GZ/" in u for u in urls)


def test_parse_abgeschlossene_index_lists_many():
    # the abgeschlossene landing page lists ALL proceedings directly (no per-year subpages)
    html = (FIXTURES / "abgeschlossene_verfahren.html").read_text(encoding="utf-8")
    urls = parse_index_page(html, base_url=AV)
    assert len(urls) > 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_parse_index.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Reuses `_effective_base` from Task 5. Real proceeding links look like
`href="DE/Beschlusskammern/1_GZ/BK6-GZ/2023/BK6-23-241/BK6-23-241_konsultation.html?nn=875510"`
— note the `?nn=` query, so filter on **`.html` contained** (not ends-with), and key on the
`/BK6-GZ/` path segment (which excludes nav links like `BK6_AV.html`).

```python
def parse_index_page(html: str, base_url: str) -> list[str]:
    """Return absolute URLs of proceeding pages linked from an index page."""
    soup = BeautifulSoup(html, "lxml")
    base = _effective_base(soup, base_url)
    urls: list[str] = []
    for anchor in soup.select("a[href]"):
        href = anchor["href"]
        if "/BK6-GZ/" in href and ".html" in href:
            urls.append(urljoin(base, href))
    # dedupe, preserve order
    return list(dict.fromkeys(urls))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `tox -e tests -- unittests/test_parse_index.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/parse.py unittests/test_parse_index.py
git commit -m "feat: parse BK6 index pages into proceeding URLs"
```

---

## Task 7: HTML normalization (`normalize.py`)

**Files:**
- Create: `src/bnetza_bk6_scraper/normalize.py`
- Test: `unittests/test_normalize.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path
from bnetza_bk6_scraper.normalize import normalize_html

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalize_keeps_content_drops_chrome():
    html = (FIXTURES / "proceeding_BK6-23-241_konsultation.html").read_text(encoding="utf-8")
    out = normalize_html(html)
    assert "Redispatch 2.0" in out          # main content kept
    assert "<script" not in out.lower()      # scripts stripped
    assert "<nav" not in out.lower()         # nav stripped
    # deterministic: normalizing twice yields identical output
    assert normalize_html(html) == out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_normalize.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Extract the main content container — **confirmed during Task 4 to be `#content`** on BNetzA proceeding pages (there is no `<main>`); the `#content` selector in `_MAIN_SELECTORS` below handles it. Drop `script`/`style`/`nav`/`header`/`footer`, and return a `prettify()`-stable string. If no main container is found, fall back to `<body>`.

```python
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
```

- [ ] **Step 4: Run test; adjust `_MAIN_SELECTORS` against the fixture until it passes**

Run: `tox -e tests -- unittests/test_normalize.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/normalize.py unittests/test_normalize.py
git commit -m "feat: add HTML normalization for stable snapshots"
```

---

## Task 8: Async fetch layer (`fetch.py`)

**Files:**
- Create: `src/bnetza_bk6_scraper/fetch.py`
- Test: `unittests/test_fetch.py`

- [ ] **Step 1: Write the failing test (using aioresponses)**

```python
import pytest
from aioresponses import aioresponses
from bnetza_bk6_scraper.fetch import Fetcher


@pytest.mark.asyncio
async def test_fetch_text_returns_body():
    url = "https://www.bundesnetzagentur.de/x.html"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body="<html>ok</html>")
        async with Fetcher(concurrency=2) as fetcher:
            body = await fetcher.get_text(url)
    assert body == "<html>ok</html>"


@pytest.mark.asyncio
async def test_fetch_bytes_returns_content():
    url = "https://www.bundesnetzagentur.de/x.pdf"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body=b"%PDF-1.7")
        async with Fetcher() as fetcher:
            data = await fetcher.get_bytes(url)
    assert data.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_fetch_retries_on_transient_error():
    url = "https://www.bundesnetzagentur.de/flaky.html"
    with aioresponses() as mocked:
        mocked.get(url, status=503)
        mocked.get(url, status=200, body="recovered")
        async with Fetcher(max_retries=2, backoff_seconds=0) as fetcher:
            body = await fetcher.get_text(url)
    assert body == "recovered"


@pytest.mark.asyncio
async def test_fetch_retries_on_waf_block_page():
    # BNetzA's WAF returns its rejection page with HTTP 200 — must be retried, not accepted.
    url = "https://www.bundesnetzagentur.de/blocked.html"
    with aioresponses() as mocked:
        mocked.get(url, status=200, body="... The requested URL was rejected ...")
        mocked.get(url, status=200, body="real content")
        async with Fetcher(max_retries=2, backoff_seconds=0) as fetcher:
            body = await fetcher.get_text(url)
    assert body == "real content"


def test_browser_user_agent_configured():
    # The WAF blocks non-browser UAs; the default headers must look like a browser.
    from bnetza_bk6_scraper.fetch import _HEADERS
    assert "Mozilla/5.0" in _HEADERS["User-Agent"]
```

`pytest-asyncio` and `asyncio_mode = "auto"` were already added to `pyproject.toml` in Task 1, so these `@pytest.mark.asyncio` tests run without further config.

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_fetch.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

**CRITICAL (confirmed during Task 4):** BNetzA sits behind a WAF that returns a **200 OK block
page** ("Die angeforderte URL wurde abgewiesen / The requested URL was rejected. Your support
ID is: …") whenever the request looks like a bot. A descriptive bot User-Agent gets blocked; a
**browser-like User-Agent plus `Accept`/`Accept-Language` headers gets through**. The headers
below are required — do not replace them with a custom bot UA. Because the block page returns
status 200, also guard against it: if a response body contains the rejection marker, treat it
as a transient failure and retry.

```python
"""Polite async HTTP client for the BNetzA site."""

from __future__ import annotations

import asyncio

import aiohttp

# BNetzA's WAF blocks non-browser User-Agents (returns a 200 "URL was rejected" page).
# A browser-like UA + Accept headers are required to receive real content.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
}
_TRANSIENT = {429, 500, 502, 503, 504}
_WAF_BLOCK_MARKER = "The requested URL was rejected"


class WafBlockedError(aiohttp.ClientError):
    """Raised when the WAF returns its 200-status rejection page, so it is retried."""


class Fetcher:
    """Bounded-concurrency aiohttp wrapper with retry/backoff."""

    def __init__(self, concurrency: int = 4, max_retries: int = 3, backoff_seconds: float = 1.0) -> None:
        self._semaphore = asyncio.Semaphore(concurrency)
        self._max_retries = max_retries
        self._backoff = backoff_seconds
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "Fetcher":
        self._session = aiohttp.ClientSession(headers=_HEADERS)
        return self

    async def __aexit__(self, *exc) -> None:
        assert self._session is not None
        await self._session.close()

    async def _fetch(self, url: str, as_text: bool) -> str | bytes:
        """GET with retry/backoff. Reads the body inside the loop so the WAF 200-block
        page (only detectable in the body of a text response) can be retried too."""
        assert self._session is not None
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            async with self._semaphore:
                try:
                    async with self._session.get(url) as resp:
                        if resp.status in _TRANSIENT:
                            raise aiohttp.ClientResponseError(
                                resp.request_info, resp.history, status=resp.status
                            )
                        resp.raise_for_status()
                        if as_text:
                            text = await resp.text()
                            if _WAF_BLOCK_MARKER in text:
                                raise WafBlockedError(url)
                            return text
                        return await resp.read()
                except aiohttp.ClientError as exc:
                    last_exc = exc
            if attempt < self._max_retries:
                await asyncio.sleep(self._backoff * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    async def get_text(self, url: str) -> str:
        result = await self._fetch(url, as_text=True)
        assert isinstance(result, str)
        return result

    async def get_bytes(self, url: str) -> bytes:
        result = await self._fetch(url, as_text=False)
        assert isinstance(result, bytes)
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `tox -e tests -- unittests/test_fetch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/fetch.py unittests/test_fetch.py pyproject.toml
git commit -m "feat: add polite async fetch layer with retry"
```

---

## Task 9: Discovery — enumerate all proceeding URLs (`discovery.py`)

**Files:**
- Create: `src/bnetza_bk6_scraper/discovery.py`
- Test: `unittests/test_discovery.py`

Discovery: fetch the two index surfaces (laufende + abgeschlossene) and collect all proceeding
URLs from them via `parse_index_page`. **Confirmed during Task 4:** the abgeschlossene landing
page lists ALL proceedings directly (430+ links) — there are **no per-year subpages** to crawl,
so discovery is just two fetches.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from aioresponses import aioresponses
from pathlib import Path
from bnetza_bk6_scraper.discovery import discover_proceeding_urls
from bnetza_bk6_scraper import discovery
from bnetza_bk6_scraper.fetch import Fetcher

FIXTURES = Path(__file__).parent / "fixtures"
LV = discovery.LAUFENDE_URL
AV = discovery.ABGESCHLOSSENE_URL


@pytest.mark.asyncio
async def test_discover_collects_urls_from_both_surfaces():
    lv_html = (FIXTURES / "laufende_verfahren.html").read_text(encoding="utf-8")
    av_html = (FIXTURES / "abgeschlossene_verfahren.html").read_text(encoding="utf-8")
    with aioresponses() as mocked:
        mocked.get(LV, status=200, body=lv_html)
        mocked.get(AV, status=200, body=av_html)
        async with Fetcher() as fetcher:
            urls = await discover_proceeding_urls(fetcher)
    assert len(urls) > 100                          # abgeschlossene alone contributes 400+
    assert all("/BK6-GZ/" in u for u in urls)
    assert len(urls) == len(set(urls))              # de-duplicated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_discovery.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
"""Enumerate BK6 proceeding URLs from the laufende and abgeschlossene index surfaces."""

from __future__ import annotations

from bnetza_bk6_scraper.fetch import Fetcher
from bnetza_bk6_scraper.parse import parse_index_page

_BASE = "https://www.bundesnetzagentur.de"
LAUFENDE_URL = f"{_BASE}/DE/Beschlusskammern/BK06/BK6_11_LV/BK6_LV.html"
ABGESCHLOSSENE_URL = f"{_BASE}/DE/Beschlusskammern/BK06/BK6_21_AV/BK6_AV.html"


async def discover_proceeding_urls(fetcher: Fetcher) -> list[str]:
    """Return the de-duplicated set of proceeding page URLs across both index surfaces."""
    collected: list[str] = []
    for index_url in (LAUFENDE_URL, ABGESCHLOSSENE_URL):
        html = await fetcher.get_text(index_url)
        collected += parse_index_page(html, base_url=index_url)
    return list(dict.fromkeys(collected))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `tox -e tests -- unittests/test_discovery.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/discovery.py unittests/test_discovery.py
git commit -m "feat: discover BK6 proceeding URLs from both index surfaces"
```

---

## Task 10: Orchestrator — `BnetzaBk6Scraper.mirror()` (`scraper.py`)

Groups discovered URLs by Aktenzeichen (aggregating phase pages), downloads PDFs, writes the on-disk tree + `index.json`. Continues past per-proceeding failures with a warning.

**Files:**
- Create: `src/bnetza_bk6_scraper/scraper.py`
- Modify: `src/bnetza_bk6_scraper/__init__.py` (export `BnetzaBk6Scraper`)
- Test: `unittests/test_scraper.py`

- [ ] **Step 1: Write the failing integration test**

```python
import json
import pytest
from pathlib import Path
from aioresponses import aioresponses
from bnetza_bk6_scraper.scraper import BnetzaBk6Scraper
from bnetza_bk6_scraper import discovery

LV = discovery.LAUFENDE_URL
AV = discovery.ABGESCHLOSSENE_URL
PROC_URL = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/BK6-23-241/BK6-23-241_konsultation.html"
PDF_URL = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/1_GZ/BK6-GZ/2023/BK6-23-241/BK6-23-241_konsultationsdokument.pdf"


FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.asyncio
async def test_mirror_writes_expected_tree(tmp_path):
    proc_html = (FIXTURES / "proceeding_BK6-23-241_konsultation.html").read_text(encoding="utf-8")
    # a minimal laufende index that links exactly one proceeding; empty abgeschlossene
    lv_html = f'<html><body><a href="{PROC_URL}">BK6-23-241</a></body></html>'
    with aioresponses() as mocked:
        mocked.get(LV, status=200, body=lv_html)
        mocked.get(AV, status=200, body="<html><body></body></html>")
        mocked.get(PROC_URL, status=200, body=proc_html)
        mocked.get(PDF_URL, status=200, body=b"%PDF-1.7 fake")
        scraper = BnetzaBk6Scraper()
        await scraper.mirror(tmp_path)

    folder = tmp_path / "2023" / "BK6-23-241"
    assert (folder / "metadata.json").exists()
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    assert meta["aktenzeichen"] == "BK6-23-241"
    assert (folder / "BK6-23-241_konsultationsdokument.pdf").read_bytes().startswith(b"%PDF")
    assert list(folder.glob("*.html"))  # normalized snapshot written
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert any(entry["aktenzeichen"] == "BK6-23-241" for entry in index)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_scraper.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
"""Orchestrates discovery, download, and writing of the BK6 mirror."""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from pathlib import Path

from bnetza_bk6_scraper.discovery import discover_proceeding_urls
from bnetza_bk6_scraper.fetch import Fetcher
from bnetza_bk6_scraper.models import Proceeding, ProceedingPage
from bnetza_bk6_scraper.normalize import normalize_html
from bnetza_bk6_scraper.parse import aktenzeichen_from_url, parse_proceeding_page, phase_from_url

_logger = logging.getLogger(__name__)


class BnetzaBk6Scraper:
    """Mirrors BK6 proceedings into a structured directory tree."""

    def __init__(self, concurrency: int = 4) -> None:
        self._concurrency = concurrency

    async def mirror(self, target_dir: str | Path, year: int | None = None) -> list[Proceeding]:
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)
        proceedings: list[Proceeding] = []

        async with Fetcher(concurrency=self._concurrency) as fetcher:
            urls = await discover_proceeding_urls(fetcher)
            by_az: dict[str, list[str]] = defaultdict(list)
            for url in urls:
                by_az[aktenzeichen_from_url(url)].append(url)

            for aktenzeichen, page_urls in by_az.items():
                if year is not None and not aktenzeichen.startswith(f"BK6-{year % 100:02d}-"):
                    continue
                try:
                    proceeding = await self._mirror_proceeding(fetcher, aktenzeichen, page_urls, target)
                    proceedings.append(proceeding)
                except Exception:  # pylint: disable=broad-except
                    _logger.warning("failed to mirror %s", aktenzeichen, exc_info=True)

        self._write_index(target, proceedings)
        doc_count = sum(len(p.documents) for p in proceedings)
        failures = len(by_az) - len(proceedings)
        _logger.info(
            "run summary: %d proceedings, %d documents written, %d failures",
            len(proceedings), doc_count, failures,
        )
        return proceedings

    async def _mirror_proceeding(self, fetcher, aktenzeichen, page_urls, target) -> Proceeding:
        merged: Proceeding | None = None
        pages: list[ProceedingPage] = []
        for url in page_urls:
            html = await fetcher.get_text(url)
            parsed = parse_proceeding_page(html, source_url=url)
            phase = phase_from_url(url)  # robust: strips any ?nn= query before deriving phase
            pages.append(ProceedingPage(phase=phase, source_url=url))
            folder = target / str(parsed.year) / aktenzeichen
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{aktenzeichen}_{phase}.html").write_text(normalize_html(html), encoding="utf-8")
            if merged is None:
                merged = parsed
            else:
                seen = {d.filename for d in merged.documents}
                merged.documents += [d for d in parsed.documents if d.filename not in seen]
        assert merged is not None
        merged.pages = pages

        folder = target / str(merged.year) / aktenzeichen
        for doc in merged.documents:
            data = await fetcher.get_bytes(doc.source_url)
            (folder / doc.filename).write_bytes(data)
        (folder / "metadata.json").write_text(
            json.dumps(merged.model_dump(mode="json"), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return merged

    @staticmethod
    def _write_index(target: Path, proceedings: list[Proceeding]) -> None:
        index = [
            {
                "aktenzeichen": p.aktenzeichen,
                "year": p.year,
                "title": p.title,
                "status": p.status,
                "stand": p.stand.isoformat() if p.stand else None,
                "path": f"{p.year}/{p.aktenzeichen}",
            }
            for p in sorted(proceedings, key=lambda p: p.aktenzeichen)
        ]
        (target / "index.json").write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )
```

Export in `__init__.py`:

```python
from bnetza_bk6_scraper.models import Document, Proceeding
from bnetza_bk6_scraper.scraper import BnetzaBk6Scraper

__all__ = ["BnetzaBk6Scraper", "Proceeding", "Document"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `tox -e tests -- unittests/test_scraper.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/scraper.py src/bnetza_bk6_scraper/__init__.py unittests/test_scraper.py
git commit -m "feat: add mirror orchestrator writing structured tree and index.json"
```

---

## Task 11: Typer CLI (`cli.py`)

**Files:**
- Create: `src/bnetza_bk6_scraper/cli.py`
- Test: `unittests/test_cli.py`

- [ ] **Step 1: Write the failing test (CliRunner + patched scraper)**

```python
from unittest.mock import AsyncMock, patch
from typer.testing import CliRunner
from bnetza_bk6_scraper.cli import app

runner = CliRunner()


def test_mirror_command_invokes_scraper(tmp_path):
    with patch("bnetza_bk6_scraper.cli.BnetzaBk6Scraper") as scraper_cls:
        scraper_cls.return_value.mirror = AsyncMock(return_value=[])
        result = runner.invoke(app, ["mirror", "--target", str(tmp_path), "--concurrency", "2"])
    assert result.exit_code == 0
    scraper_cls.return_value.mirror.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `tox -e tests -- unittests/test_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

```python
"""Command-line interface for the BK6 scraper."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import typer

from bnetza_bk6_scraper.scraper import BnetzaBk6Scraper

app = typer.Typer(help="Mirror Bundesnetzagentur Beschlusskammer 6 documents.")


@app.command()
def mirror(
    target: Path = typer.Option(..., "--target", help="Output directory (mirror repo root)."),
    concurrency: int = typer.Option(4, "--concurrency", help="Parallel fetches."),
    year: int | None = typer.Option(None, "--year", help="Restrict to a single year."),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Debug logging."),
) -> None:
    """Download BK6 proceedings into TARGET as a structured, diffable tree."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    scraper = BnetzaBk6Scraper(concurrency=concurrency)
    asyncio.run(scraper.mirror(target, year=year))


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `tox -e tests -- unittests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/cli.py unittests/test_cli.py
git commit -m "feat: add Typer CLI mirror command"
```

---

## Task 12: Full verification, README, and quality gates

**Files:**
- Modify: `README.md`
- Modify: `domain-specific-terms.txt` (add BNetzA/BK6/Aktenzeichen terms for codespell)

- [ ] **Step 1: Run the full quality suite**

Run: `tox` (runs tests, coverage ≥80%, pylint 10/10, mypy, black, isort, codespell)
Expected: all green. Fix lint/type/format issues; add domain terms to `domain-specific-terms.txt` for any codespell false positives (e.g. `Aktenzeichen`, `Verfahren`, `Beschlusskammer`).

- [ ] **Step 2: Smoke-test the CLI against the live site (one year)**

Run: `.tox/dev/bin/bnetza-bk6-scraper mirror --target ./_smoke --year 2023 -v` (Windows: `.tox\dev\Scripts\bnetza-bk6-scraper ...`)
Expected: `_smoke/2023/BK6-.../metadata.json` and PDFs appear; delete `_smoke/` afterwards (do not commit it — add to `.gitignore` if needed).

- [ ] **Step 3: Rewrite README** for the scraper: what it does, install, CLI usage, output layout, and a "Mirror repo" section describing the planned `bnetza_bk6_mirror` GitHub Action (cron → `pip install bnetza_bk6_scraper` → `bnetza-bk6-scraper mirror --target .` → commit).

- [ ] **Step 4: Commit**

```bash
git add README.md domain-specific-terms.txt .gitignore
git commit -m "docs: document bnetza_bk6_scraper usage and quality gates"
```

---

## Notes for the implementer

- **Fixtures drive the parsers.** Tasks 5–7 and 9 depend on the *real* BNetzA DOM. The selectors in this plan are informed starting points — inspect the Task 4 fixtures and adjust. When a selector is wrong, the test tells you.
- **`pytest-asyncio`** must be in the `tests` extra with `asyncio_mode = "auto"` (add under `[tool.pytest.ini_options]`), otherwise the async tests won't run.
- **DRY:** all parse helpers live in `parse.py`; the fetch policy lives only in `fetch.py`.
- **YAGNI:** no smart caching, no multi-chamber abstraction, no mirror-repo code in this cycle.
