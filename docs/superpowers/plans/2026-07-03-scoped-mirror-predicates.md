# Scoped Mirroring via Seed Pages + Predicates — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a caller mirror only a curated subset of BK6 documents by supplying seed page URLs + a list of OR-combined predicate functions, keeping the scraper generic (policy lives in a mirror-repo driver script).

**Architecture:** Add a generic bounded crawler (`crawl_candidates`) that walks caller-supplied seed pages to a bounded depth and yields `CandidateDocument`s, plus a `mirror_seeds` orchestrator that downloads every candidate accepted by any predicate and writes it under an Aktenzeichen-keyed path (or a generic `_other/` path when it has no Aktenzeichen). The existing full-index `mirror(...)` path and CLI are untouched.

**Tech Stack:** Python 3.11+, `aiohttp` (existing `Fetcher`), `beautifulsoup4`+`lxml`, `pydantic` v2, `pytest`+`pytest-asyncio`+`aioresponses`. Lint/type/coverage via `tox` (pylint 10/10, mypy `--strict`, coverage ~98%).

**Spec:** `docs/superpowers/specs/2026-07-03-scoped-mirror-predicates-design.md`

**Status (2026-07-03):** Brainstorm ✅, spec ✅ (reviewed), plan ✅ (reviewed). **Not yet
implemented** — Tasks 1–8 below are unstarted. Resume with the subagent-driven-development
skill, one task at a time, checking the boxes as you go.

## Environment note

On this machine `tox` needs `packaging>=25.1` globally or it fails to start with
`ModuleNotFoundError: No module named 'packaging.pylock'`. If a `tox` run errors that way,
run `python -m pip install --upgrade "packaging>=25.1"` once, then re-run. Per-task
verification uses `tox -e tests`; full gate at the end runs bare `tox`.

## File structure

| File | Change | Responsibility |
|---|---|---|
| `src/bnetza_bk6_scraper/models.py` | modify | Add `CandidateDocument` pydantic model. |
| `src/bnetza_bk6_scraper/parse.py` | modify | Add `parse_candidate_documents()` (PDF anchors → candidates) and `parse_followable_links()` (HTML anchors → absolute URLs). Reuse existing private helpers. |
| `src/bnetza_bk6_scraper/discovery.py` | modify | Add async `crawl_candidates()` — bounded BFS over seeds. |
| `src/bnetza_bk6_scraper/scraper.py` | modify | Add `mirror_seeds()` + `_relative_path_for()` layout helper + manifest write. |
| `src/bnetza_bk6_scraper/__init__.py` | modify | Export `CandidateDocument`. |
| `unittests/test_models.py` | modify | `CandidateDocument` construction/defaults. |
| `unittests/test_parse_candidates.py` | create | Candidate + followable-link extraction. |
| `unittests/test_crawl.py` | create | Bounded crawler behavior. |
| `unittests/test_scraper_seeds.py` | create | `mirror_seeds` end-to-end (mocked HTTP). |
| `README.md` | modify | Short "Scoped mirroring (Python API)" section. |

## Key decisions locked from the spec (do not re-litigate)

- Predicate signature: `Callable[[CandidateDocument], bool]`; OR semantics; `keep` is a
  **required** arg; empty list ⇒ keep nothing.
- Layout: Aktenzeichen docs → `target/<year>/<aktenzeichen>/<filename>` (existing convention);
  non-Aktenzeichen docs → `target/_other/<path-after-/BK06/>/<filename>`.
- `mirror_seeds` writes a single root `manifest.json` listing kept docs (no per-proceeding
  `metadata.json`, no page-HTML snapshot — this is the "minimal metadata" resolution of the
  spec's open question 1).
- Default `url_prefixes` (when `None`) = each seed's own directory URL (everything up to and
  including its last `/`), so a shallow crawl stays local to the seeded topic.
- Default `max_depth=1`.

---

### Task 1: `CandidateDocument` model

**Files:**
- Modify: `src/bnetza_bk6_scraper/models.py`
- Test: `unittests/test_models.py`

- [ ] **Step 1: Write the failing test** — append to `unittests/test_models.py`:

```python
def test_candidate_document_defaults() -> None:
    from bnetza_bk6_scraper.models import CandidateDocument

    c = CandidateDocument(
        source_url="https://x/DE/Beschlusskammern/BK06/a/PID_1.pdf",
        filename="PID_1.pdf",
        title="Anwendungsübersicht der Prüfidentifikatoren",
        found_on="https://x/DE/Beschlusskammern/BK06/a/index.html",
    )
    assert c.aktenzeichen is None
    assert c.doc_type is None


def test_candidate_document_with_aktenzeichen() -> None:
    from bnetza_bk6_scraper.models import CandidateDocument

    c = CandidateDocument(
        source_url="https://x/BK6-GZ/2024/BK6-24-174/Beschluss/BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        filename="BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        title="GPKE Teil 1 (Lesefassung)",
        found_on="https://x/gpke_node.html",
        aktenzeichen="BK6-24-174",
        doc_type="GPKE_Teil1_Lesefassung",
    )
    assert c.aktenzeichen == "BK6-24-174"
    assert c.doc_type == "GPKE_Teil1_Lesefassung"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_models.py -k candidate -v`
Expected: FAIL (ImportError: cannot import name `CandidateDocument`).

- [ ] **Step 3: Add the model** — in `src/bnetza_bk6_scraper/models.py`, after the `Document` class:

```python
class CandidateDocument(BaseModel):
    """A downloadable document discovered while crawling seed pages, before any predicate
    has decided whether to keep it. Carries enough context for a predicate to decide
    without fetching the file first."""

    source_url: str
    """Absolute URL of the linked file (may carry a ``?__blob=publicationFile&v=…`` query)."""

    filename: str
    """Bare filename, e.g. ``"BK6-24-174_GPKE_Teil1_Lesefassung.pdf"``."""

    title: str
    """Anchor link text (falls back to the filename when the anchor has no text)."""

    found_on: str
    """URL of the page this link was discovered on — gives topic/framework context."""

    aktenzeichen: str | None = None
    """Proceeding Aktenzeichen parsed from the URL path, or ``None`` (e.g. PID docs in the
    Datenformate tree carry no Aktenzeichen)."""

    doc_type: str | None = None
    """Document-type slug parsed from the filename after the Aktenzeichen prefix, or ``None``
    when the URL carries no Aktenzeichen."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_models.py -k candidate -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/models.py unittests/test_models.py
git commit -m "feat: add CandidateDocument model"
```

---

### Task 2: candidate + followable-link extraction

**Files:**
- Modify: `src/bnetza_bk6_scraper/parse.py`
- Test: `unittests/test_parse_candidates.py` (create)

Reuse existing helpers in `parse.py`: `_effective_base`, `filename_from_pdf_url`,
`_doc_type_from_filename`, `aktenzeichen_from_url`, `_attr_str`.

- [ ] **Step 1: Write the failing test** — create `unittests/test_parse_candidates.py`:

```python
from bnetza_bk6_scraper.parse import parse_candidate_documents, parse_followable_links

BASE = "https://www.bundesnetzagentur.de"
GPKE_PAGE = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/gpke_node.html"

# One PDF under a proceeding (has Aktenzeichen), one PDF without (PID), one HTML sub-link.
PAGE_HTML = (
    "<html><head><base href='/'/></head><body><div id='content'>"
    "<a href='/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/BK6-24-174/Beschluss/"
    "BK6-24-174_GPKE_Teil1_Lesefassung.pdf'>GPKE Teil 1 (Lesefassung)</a>"
    "<a href='/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/835_mitteilungen_datenformate/"
    "Mitteilung_48/Anlagen/PID_3_2.pdf?__blob=publicationFile&v=1'>Prüfidentifikatoren</a>"
    "<a href='/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/detail.html'>Mehr</a>"
    "</div></body></html>"
)


def test_parse_candidate_documents_extracts_pdfs_with_context() -> None:
    cands = parse_candidate_documents(PAGE_HTML, page_url=GPKE_PAGE)
    by_name = {c.filename: c for c in cands}
    assert set(by_name) == {"BK6-24-174_GPKE_Teil1_Lesefassung.pdf", "PID_3_2.pdf"}

    gpke = by_name["BK6-24-174_GPKE_Teil1_Lesefassung.pdf"]
    assert gpke.aktenzeichen == "BK6-24-174"
    assert gpke.doc_type == "GPKE_Teil1_Lesefassung"
    assert gpke.title == "GPKE Teil 1 (Lesefassung)"
    assert gpke.found_on == GPKE_PAGE
    assert gpke.source_url.startswith(f"{BASE}/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/")

    pid = by_name["PID_3_2.pdf"]
    assert pid.aktenzeichen is None
    assert pid.doc_type is None
    assert "__blob=publicationFile" in pid.source_url


def test_parse_followable_links_returns_absolute_html_links() -> None:
    links = parse_followable_links(PAGE_HTML, page_url=GPKE_PAGE)
    assert f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/detail.html" in links
    # PDF anchors are not followable HTML links
    assert not any(link.endswith(".pdf") for link in links)


def test_parse_followable_links_deduplicates() -> None:
    html = (
        "<html><body>"
        "<a href='/a/x.html'>x</a><a href='/a/x.html'>x again</a>"
        "</body></html>"
    )
    links = parse_followable_links(html, page_url=f"{BASE}/a/index.html")
    assert links.count(f"{BASE}/a/x.html") == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_parse_candidates.py -v`
Expected: FAIL (ImportError for `parse_candidate_documents`).

- [ ] **Step 3: Implement** — in `src/bnetza_bk6_scraper/parse.py`:

Add `CandidateDocument` to the model import:
```python
from bnetza_bk6_scraper.models import CandidateDocument, Document, Proceeding
```

Add these two public functions (place after `_parse_documents`):
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_parse_candidates.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/parse.py unittests/test_parse_candidates.py
git commit -m "feat: extract candidate documents and followable links from any page"
```

---

### Task 3: bounded crawler `crawl_candidates`

**Files:**
- Modify: `src/bnetza_bk6_scraper/discovery.py`
- Test: `unittests/test_crawl.py` (create)

Behavior: BFS from `seeds`. Fetch each page's text; collect its `CandidateDocument`s; if the
current depth `< max_depth`, enqueue its followable links that (a) are on the same host and
(b) start with one of `url_prefixes`. Track visited page URLs (never re-fetch). Dedupe
returned candidates by `source_url`. When `url_prefixes` is `None`, derive it from each
seed's directory (URL up to and including the last `/`). A page fetch that raises is logged
and skipped (crawl continues).

- [ ] **Step 1: Write the failing test** — create `unittests/test_crawl.py`:

```python
import pytest
from aioresponses import aioresponses

from bnetza_bk6_scraper.discovery import crawl_candidates
from bnetza_bk6_scraper.fetch import Fetcher

BASE = "https://www.bundesnetzagentur.de"
SEED = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/gpke_node.html"
SUB = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/detail.html"
OFFSITE = "https://example.com/other.html"

SEED_HTML = (
    "<html><head><base href='/'/></head><body>"
    "<a href='/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/BK6-24-174/Beschluss/"
    "BK6-24-174_GPKE_Teil1_Lesefassung.pdf'>GPKE Teil 1</a>"
    "<a href='/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/detail.html'>Detail</a>"
    "<a href='https://example.com/other.html'>offsite</a>"
    "</body></html>"
)
SUB_HTML = (
    "<html><head><base href='/'/></head><body>"
    "<a href='/DE/Beschlusskammern/1_GZ/BK6-GZ/2022/BK6-22-024/Beschluss/"
    "Anlage1d_GPKE_Teil4.pdf'>GPKE Teil 4</a>"
    "</body></html>"
)


@pytest.mark.asyncio
async def test_depth_zero_only_reads_seed() -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        async with Fetcher() as fetcher:
            cands = await crawl_candidates(fetcher, [SEED], max_depth=0)
    names = {c.filename for c in cands}
    assert names == {"BK6-24-174_GPKE_Teil1_Lesefassung.pdf"}  # sub-page not followed


@pytest.mark.asyncio
async def test_depth_one_follows_same_prefix_subpage() -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        mocked.get(SUB, status=200, body=SUB_HTML)
        # OFFSITE intentionally NOT mocked: must never be fetched (different host/prefix)
        async with Fetcher() as fetcher:
            cands = await crawl_candidates(fetcher, [SEED], max_depth=1)
    names = {c.filename for c in cands}
    assert names == {"BK6-24-174_GPKE_Teil1_Lesefassung.pdf", "Anlage1d_GPKE_Teil4.pdf"}


@pytest.mark.asyncio
async def test_crawl_dedupes_and_survives_fetch_error() -> None:
    # SUB_HTML here links back to SEED (cycle) so the visited-guard is exercised; SEED is
    # fetched once; a broken sub-page is skipped without aborting the crawl.
    seed_html = SEED_HTML + f"<a href='{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/broken.html'>b</a>"
    sub_html_with_backlink = SUB_HTML.replace("</body>", f"<a href='{SEED}'>back</a></body>")
    broken = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/broken.html"
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=seed_html)
        mocked.get(SUB, status=200, body=sub_html_with_backlink)
        mocked.get(broken, status=500)
        mocked.get(broken, status=500)
        mocked.get(broken, status=500)
        mocked.get(broken, status=500)
        async with Fetcher(max_retries=0) as fetcher:
            cands = await crawl_candidates(fetcher, [SEED], max_depth=1)
    # both good PDFs present exactly once despite the broken sub-page
    names = sorted(c.filename for c in cands)
    assert names == ["Anlage1d_GPKE_Teil4.pdf", "BK6-24-174_GPKE_Teil1_Lesefassung.pdf"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_crawl.py -v`
Expected: FAIL (ImportError for `crawl_candidates`).

- [ ] **Step 3: Implement** — in `src/bnetza_bk6_scraper/discovery.py`:

```python
import logging
from collections import deque
from urllib.parse import urlsplit

from bnetza_bk6_scraper.models import CandidateDocument
from bnetza_bk6_scraper.parse import (
    parse_candidate_documents,
    parse_followable_links,
    parse_index_page,
)

_logger = logging.getLogger(__name__)


def _default_prefix(url: str) -> str:
    """The seed's own directory: the URL up to and including its last '/'."""
    return url.rsplit("/", 1)[0] + "/"


async def crawl_candidates(
    fetcher: Fetcher,
    seeds: list[str],
    max_depth: int = 1,
    url_prefixes: list[str] | None = None,
) -> list[CandidateDocument]:
    """Breadth-first crawl from ``seeds`` collecting every PDF link as a CandidateDocument.

    Follows same-host HTML sub-links whose URL starts with one of ``url_prefixes`` (default:
    each seed's own directory) up to ``max_depth`` levels below the seeds. Pages are fetched
    at most once; candidates are de-duplicated by ``source_url``. A page that fails to fetch
    is logged and skipped so the crawl continues.
    """
    prefixes = url_prefixes if url_prefixes is not None else [_default_prefix(s) for s in seeds]
    visited: set[str] = set()
    candidates: dict[str, CandidateDocument] = {}
    queue: deque[tuple[str, int]] = deque((seed, 0) for seed in seeds)

    while queue:
        url, depth = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        try:
            html = await fetcher.get_text(url)
        except Exception:  # pylint: disable=broad-except
            _logger.warning("failed to crawl %s", url, exc_info=True)
            continue
        for cand in parse_candidate_documents(html, page_url=url):
            candidates.setdefault(cand.source_url, cand)
        if depth < max_depth:
            for link in parse_followable_links(html, page_url=url):
                if link in visited:
                    continue
                same_host = urlsplit(link).netloc == urlsplit(url).netloc
                if same_host and any(link.startswith(p) for p in prefixes):
                    queue.append((link, depth + 1))
    return list(candidates.values())
```

(Keep the existing `discover_proceeding_urls` and its imports; just add the above.)

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_crawl.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/discovery.py unittests/test_crawl.py
git commit -m "feat: bounded seed-page crawler yielding CandidateDocuments"
```

---

### Task 4: `mirror_seeds` orchestrator + layout

**Files:**
- Modify: `src/bnetza_bk6_scraper/scraper.py`
- Test: `unittests/test_scraper_seeds.py` (create)

- [ ] **Step 1: Write the failing test** — create `unittests/test_scraper_seeds.py`:

```python
import json
from pathlib import Path

import pytest
from aioresponses import aioresponses

from bnetza_bk6_scraper.models import CandidateDocument
from bnetza_bk6_scraper.scraper import BnetzaBk6Scraper

BASE = "https://www.bundesnetzagentur.de"
SEED = f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/gpke_node.html"
GPKE_PDF = (
    f"{BASE}/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/BK6-24-174/Beschluss/"
    "BK6-24-174_GPKE_Teil1_Lesefassung.pdf"
)
GPKE_AENDERUNG = (
    f"{BASE}/DE/Beschlusskammern/1_GZ/BK6-GZ/2024/BK6-24-174/Beschluss/"
    "BK6-24-174_GPKE_Teil1_Aenderung.pdf"
)
PID_PDF = (
    f"{BASE}/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/835_mitteilungen_datenformate/"
    "Mitteilung_48/Anlagen/PID_3_2.pdf"
)
SEED_HTML = (
    "<html><head><base href='/'/></head><body>"
    f"<a href='{GPKE_PDF}'>GPKE Teil 1 (Lesefassung)</a>"
    f"<a href='{GPKE_AENDERUNG}'>GPKE Teil 1 (Änderungsmodus)</a>"
    f"<a href='{PID_PDF}'>Anwendungsübersicht der Prüfidentifikatoren</a>"
    "</body></html>"
)


def _keep_lesefassung(c: CandidateDocument) -> bool:
    name = c.filename.lower()
    return "gpke_" in name and "lesefassung" in name and "aenderung" not in name


def _keep_pid(c: CandidateDocument) -> bool:
    return c.filename.lower().startswith("pid_")


@pytest.mark.asyncio
async def test_mirror_seeds_writes_both_layout_branches(tmp_path: Path) -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        mocked.get(GPKE_PDF, status=200, body=b"%PDF-1.7 gpke")
        mocked.get(PID_PDF, status=200, body=b"%PDF-1.7 pid")
        # GPKE_AENDERUNG intentionally NOT mocked: no predicate keeps it, so it is never fetched.
        scraper = BnetzaBk6Scraper()
        kept = await scraper.mirror_seeds(
            tmp_path, seeds=[SEED], keep=[_keep_lesefassung, _keep_pid], max_depth=0
        )

    assert {c.filename for c in kept} == {
        "BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        "PID_3_2.pdf",
    }
    # Aktenzeichen branch
    gpke_path = tmp_path / "2024" / "BK6-24-174" / "BK6-24-174_GPKE_Teil1_Lesefassung.pdf"
    assert gpke_path.read_bytes().startswith(b"%PDF")
    # non-Aktenzeichen branch: _other/<path-after-/BK06/>/<filename>
    pid_path = (
        tmp_path / "_other" / "BK6_83_Zug_Mess" / "835_mitteilungen_datenformate"
        / "Mitteilung_48" / "Anlagen" / "PID_3_2.pdf"
    )
    assert pid_path.read_bytes().startswith(b"%PDF")
    # manifest lists both kept docs
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert {entry["filename"] for entry in manifest} == {
        "BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        "PID_3_2.pdf",
    }


@pytest.mark.asyncio
async def test_mirror_seeds_empty_keep_downloads_nothing(tmp_path: Path) -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        scraper = BnetzaBk6Scraper()
        kept = await scraper.mirror_seeds(tmp_path, seeds=[SEED], keep=[], max_depth=0)
    assert kept == []
    assert not any(tmp_path.rglob("*.pdf"))


@pytest.mark.asyncio
async def test_mirror_seeds_continues_when_one_download_fails(tmp_path: Path) -> None:
    with aioresponses() as mocked:
        mocked.get(SEED, status=200, body=SEED_HTML)
        mocked.get(GPKE_PDF, status=404)
        mocked.get(PID_PDF, status=200, body=b"%PDF-1.7 pid")
        # backoff_seconds=0 so the retried 404 fails fast instead of sleeping ~6s
        scraper = BnetzaBk6Scraper(backoff_seconds=0.0)
        kept = await scraper.mirror_seeds(
            tmp_path, seeds=[SEED], keep=[_keep_lesefassung, _keep_pid], max_depth=0
        )
    # both are "kept" (selected), but only the one that downloaded lands on disk
    assert {c.filename for c in kept} == {
        "BK6-24-174_GPKE_Teil1_Lesefassung.pdf",
        "PID_3_2.pdf",
    }
    assert not (tmp_path / "2024" / "BK6-24-174" / "BK6-24-174_GPKE_Teil1_Lesefassung.pdf").exists()
    assert (
        tmp_path / "_other" / "BK6_83_Zug_Mess" / "835_mitteilungen_datenformate"
        / "Mitteilung_48" / "Anlagen" / "PID_3_2.pdf"
    ).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_scraper_seeds.py -v`
Expected: FAIL (`AttributeError: 'BnetzaBk6Scraper' object has no attribute 'mirror_seeds'`).

- [ ] **Step 3: Implement** — in `src/bnetza_bk6_scraper/scraper.py`:

Adjust imports. `scraper.py` already imports `crawl`-free `discovery`, `models`
(`Proceeding`, `ProceedingPage`), `parse` (`aktenzeichen_from_url`, `parse_proceeding_page`,
`phase_from_url`, `year_from_aktenzeichen`), `json`, `logging`, `Path`. Make exactly these
additions — do not rewrite the existing import lines:

1. Add two stdlib imports at the top:
```python
from collections.abc import Callable
from urllib.parse import urlsplit
```
2. On the existing `from bnetza_bk6_scraper.discovery import ...` line, add `crawl_candidates`.
3. On the existing `from bnetza_bk6_scraper.models import ...` line, add `CandidateDocument`.

`year_from_aktenzeichen` (used by `_relative_path_for`) is already imported — no parse-import
change is needed.

Extend `BnetzaBk6Scraper.__init__` to accept optional retry knobs (additive; existing callers
unaffected) and stash them so both `mirror` and `mirror_seeds` can pass them to `Fetcher`:
```python
    def __init__(
        self, concurrency: int = 4, max_retries: int = 3, backoff_seconds: float = 1.0
    ) -> None:
        self._concurrency = concurrency
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
```
(Update the existing `mirror` method's `Fetcher(concurrency=self._concurrency)` call to also
pass `max_retries=self._max_retries, backoff_seconds=self._backoff_seconds` — keeps the two
paths consistent.)

Add a module-level layout helper (after the imports, before the class):
```python
def _relative_path_for(candidate: CandidateDocument) -> Path:
    """Mirror-tree path for a kept candidate.

    Aktenzeichen docs go under ``<year>/<aktenzeichen>/`` (the existing convention). Docs
    without an Aktenzeichen go under ``_other/<path-after-/BK06/>/`` so the layout is a pure
    function of the source URL and hardcodes no topic names."""
    if candidate.aktenzeichen is not None:
        year = year_from_aktenzeichen(candidate.aktenzeichen)
        return Path(str(year)) / candidate.aktenzeichen / candidate.filename
    path = urlsplit(candidate.source_url).path
    marker = "/BK06/"
    tail = path.split(marker, 1)[1] if marker in path else path.lstrip("/")
    # tail includes the filename; rebuild as directory parts + filename
    parts = [p for p in tail.split("/") if p]
    return Path("_other", *parts)
```

Add the method to `BnetzaBk6Scraper`:
```python
    async def mirror_seeds(
        self,
        target_dir: str | Path,
        seeds: list[str],
        keep: list[Callable[[CandidateDocument], bool]],
        max_depth: int = 1,
        url_prefixes: list[str] | None = None,
    ) -> list[CandidateDocument]:
        """Crawl ``seeds`` and download every discovered document accepted by any predicate.

        ``keep`` predicates combine with OR semantics: a candidate is downloaded iff at least
        one predicate returns True. An empty ``keep`` keeps nothing. Aktenzeichen docs are
        written under ``<year>/<aktenzeichen>/``; others under ``_other/…`` (see
        :func:`_relative_path_for`). A root ``manifest.json`` lists the kept documents.
        """
        target = Path(target_dir)
        target.mkdir(parents=True, exist_ok=True)

        async with Fetcher(
            concurrency=self._concurrency,
            max_retries=self._max_retries,
            backoff_seconds=self._backoff_seconds,
        ) as fetcher:
            candidates = await crawl_candidates(fetcher, seeds, max_depth, url_prefixes)
            kept = [c for c in candidates if any(pred(c) for pred in keep)]
            written: list[CandidateDocument] = []
            for cand in kept:
                dest = target / _relative_path_for(cand)
                try:
                    data = await fetcher.get_bytes(cand.source_url)
                except Exception:  # pylint: disable=broad-except
                    _logger.warning("failed to download %s", cand.source_url, exc_info=True)
                    written.append(cand)  # selected even if the byte fetch failed
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                written.append(cand)

        self._write_manifest(target, kept)
        _logger.info(
            "seed run summary: %d candidates, %d kept, %d seeds",
            len(candidates),
            len(kept),
            len(seeds),
        )
        return kept

    @staticmethod
    def _write_manifest(target: Path, kept: list[CandidateDocument]) -> None:
        """Write manifest.json summarizing the kept documents and where they were written."""
        manifest = [
            {
                "filename": c.filename,
                "title": c.title,
                "aktenzeichen": c.aktenzeichen,
                "doc_type": c.doc_type,
                "source_url": c.source_url,
                "found_on": c.found_on,
                "path": str(_relative_path_for(c)).replace("\\", "/"),
            }
            for c in sorted(kept, key=lambda c: str(_relative_path_for(c)))
        ]
        (target / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
```

Notes for the implementer:
- `json`, `logging` (`_logger`), `Fetcher`, `Path` are already imported in `scraper.py`.
- The test uses `keep=[]`; ensure the empty-list path writes an empty `manifest.json` and no
  PDFs (it will, since `kept` is empty).
- `_relative_path_for` returning a `Path` built with `_other` uses OS separators; the manifest
  normalizes to `/` for a stable, diff-friendly, cross-platform value.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_scraper_seeds.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/scraper.py unittests/test_scraper_seeds.py
git commit -m "feat: mirror_seeds orchestrator with OR predicates and dual layout"
```

---

### Task 5: public export + README

**Files:**
- Modify: `src/bnetza_bk6_scraper/__init__.py`
- Modify: `README.md`
- Test: `unittests/test_models.py` (add import-surface assertion)

- [ ] **Step 1: Write the failing test** — append to `unittests/test_models.py`:

```python
def test_candidate_document_is_publicly_exported() -> None:
    import bnetza_bk6_scraper as pkg

    assert "CandidateDocument" in pkg.__all__
    assert pkg.CandidateDocument is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest unittests/test_models.py -k exported -v`
Expected: FAIL (`CandidateDocument` not in `__all__` / AttributeError).

- [ ] **Step 3: Implement** — update `src/bnetza_bk6_scraper/__init__.py`:

```python
"""bnetza_bk6_scraper: mirror Bundesnetzagentur Beschlusskammer 6 documents."""

from bnetza_bk6_scraper.models import CandidateDocument, Document, Proceeding
from bnetza_bk6_scraper.scraper import BnetzaBk6Scraper

__all__ = ["BnetzaBk6Scraper", "Proceeding", "Document", "CandidateDocument"]
```

Then add a short section to `README.md` (place after the existing CLI usage section):

````markdown
## Scoped mirroring (Python API)

The `mirror` CLI mirrors *all* proceedings. To mirror only a curated subset (e.g. the
electricity GPKE/WiM/MaBiS Prozessdokumente), use the Python API: give the scraper a list of
**seed pages** to crawl and a list of **predicates** (OR semantics — a document is downloaded
if *any* predicate returns `True`). Predicates receive a `CandidateDocument`.

```python
import asyncio
from bnetza_bk6_scraper import BnetzaBk6Scraper, CandidateDocument

GPKE = "https://www.bundesnetzagentur.de/DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/831_gpke/gpke_node.html"

def is_prozessdokument_lesefassung(c: CandidateDocument) -> bool:
    name = c.filename.lower()
    return any(fw in name for fw in ("_gpke_", "_wim_", "_mabis_")) and "lesefassung" in name

asyncio.run(
    BnetzaBk6Scraper().mirror_seeds(
        target_dir=".", seeds=[GPKE], keep=[is_prozessdokument_lesefassung]
    )
)
```

Documents that carry an Aktenzeichen are written under `<year>/<aktenzeichen>/`; documents
without one (e.g. the PID-Liste in the Datenformate tree) go under `_other/…`.
````

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest unittests/test_models.py -k exported -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/bnetza_bk6_scraper/__init__.py README.md unittests/test_models.py
git commit -m "feat: export CandidateDocument; document scoped mirroring API"
```

---

### Task 6: Full quality gate

**Files:** none (verification only).

- [ ] **Step 1: Run the full tox gate**

Run: `tox`
Expected: all environments pass — `tests` (all unittests green), `linting` (pylint 10.00/10),
`type_check` (mypy `--strict` clean), `coverage` at/above the repo bar, `spell_check` clean.
If `tox` fails to start with `packaging.pylock`, run
`python -m pip install --upgrade "packaging>=25.1"` and retry.

- [ ] **Step 2: Fix any findings** (lint/type/spell/coverage). Likely spots:
  - `domain-specific-terms.txt` may need new words (e.g. `Lesefassung`, `Aenderung`,
    `Prozessdokument`, `Datenformate`, `Prüfidentifikatoren`) for `spell_check`.
  - mypy: ensure `Callable` import and the `list[Callable[[CandidateDocument], bool]]` annotation
    are correct; `_relative_path_for` returns `Path`.
  - Coverage: add a small test if a branch (e.g. the `marker not in path` fallback in
    `_relative_path_for`) is uncovered.

- [ ] **Step 3: Commit any fixes**

```bash
git add -A
git commit -m "chore: satisfy lint/type/spell/coverage for scoped mirroring"
```

---

### Task 7: Independent review (per user instruction)

- [ ] **Step 1:** Invoke `superpowers:requesting-code-review` for the branch diff vs `main`.
- [ ] **Step 2:** Triage findings via `superpowers:receiving-code-review` (verify before acting);
  apply fixes as small TDD commits; re-run `tox`.
- [ ] **Step 3:** Open the PR on `bnetza_bk6_scraper` (feature branch → `main`).

---

### Task 8: Release + mirror-repo cleanup (per user instruction — separate repo)

> This runs **after** the scraper PR is merged and the review is complete. It touches the
> **`Hochfrequenz/bnetza_bk6_mirror`** repo at `C:\github\bnetza_bk6_mirror`, not this one.

- [ ] **Step 1: Cut the release (version bump).** Version is hatch-vcs from git tags, so bumping
  = tagging a release. After the scraper PR merges to `main`:
  `gh release create v0.1.0 --generate-notes` (the minor bump for the additive `mirror_seeds`
  API). This triggers `python-publish.yml` → PyPI. Confirm the publish succeeded.

- [ ] **Step 2: Add the driver script** `download_and_post_process.py` to the mirror repo
  (edi_energy_mirror pattern): define `SEEDS` (GPKE / WiM / MaBiS / MaKo2022 topic pages + the
  current PID source page) and the predicates (`is_prozessdokument_lesefassung`, `is_pid_liste`),
  and call `BnetzaBk6Scraper().mirror_seeds(target_dir=".", seeds=SEEDS, keep=[...])`. Pin the
  scraper to `>=0.1.0` in `dependencies/mirror-requirements.txt`.

- [ ] **Step 3: Point `mirror.yml`** at `python download_and_post_process.py` instead of
  `bnetza-bk6-scraper mirror --target .`.

- [ ] **Step 4: Clean the mirror tree.** The repo currently holds the full BK6 back-catalogue
  (all 430+ proceedings) from the initial full-mirror runs. Since scope is now the curated
  subset, remove the out-of-scope content so the tree reflects only what the driver produces.
  Recommended: in a branch, `git rm -r` the old top-level year directories + `index.json`, run
  the new driver locally to regenerate the scoped tree + `manifest.json`, commit, and open a
  cleanup PR. **Confirm the exact deletion set with the user before force-cleaning** — this is
  a destructive, outward-facing change to a published data repo.

- [ ] **Step 5:** Verify the mirror Action runs green on the new script and opens/auto-merges its
  PR as before.

## Notes

- Do NOT modify `mirror(...)`, the `mirror` CLI, or the existing `discover_proceeding_urls` /
  `parse_*` behavior — this feature is purely additive.
- Follow the existing test style: `unittests/`, `aioresponses` for HTTP, `@pytest.mark.asyncio`,
  fixtures under `unittests/fixtures/` when a real page snapshot is needed (synthetic HTML inline
  is fine for these tasks).
- The `edi_energy_scraper` Aktivitätsdiagramme feature is a **separate** later cycle — not part
  of this plan.
