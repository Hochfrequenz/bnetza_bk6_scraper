# BNetzA Beschlusskammer 6 Scraper — Design

**Date:** 2026-07-03
**Status:** Approved (design)

## Purpose

Create an up-to-date, version-controlled mirror of the documents published by the
Bundesnetzagentur's **Beschlusskammer 6 (BK6)** — the decision chamber responsible for
access to electricity supply networks (GPKE, MaBiS, Redispatch 2.0, §14a EnWG, etc.).

Modeled on Hochfrequenz's `edi_energy_scraper` / `edi_energy_mirror` pair: a
pip-installable **scraper** package holds all logic; a separate **mirror** data repo runs
the scraper on a schedule and commits the result, so regulatory changes surface as **git
diffs**.

## Two-repo design

| Repo | Role |
|---|---|
| `bnetza_bk6_scraper` (this repo) | pip-installable package + Typer CLI containing all crawl/parse/download logic. Published to PyPI via the template's existing workflow. |
| `bnetza_bk6_mirror` (built later) | Data only, plus a scheduled GitHub Action that installs the scraper, runs it against the repo root, and commits changes. |

This spec covers the **scraper** repo only. The mirror repo (its `mirror.yml` Action and
README) is documented here for context and built in a later cycle.

### Housekeeping (this repo starts as the Hochfrequenz Python template)

- Replace `pyproject.toml` placeholders: package name → `bnetza_bk6_scraper`, description,
  authors, keywords, project URLs.
- Rename `src/mypackage` → `src/bnetza_bk6_scraper`; remove `mymodule.py` example and the
  `test_myclass.py` example test.
- Add runtime dependencies and register the CLI entry point.

## Target site structure (as of 2026-07)

Two index surfaces enumerate proceedings:

- **Laufende Verfahren** (ongoing): `DE/Beschlusskammern/BK06/BK6_11_LV/BK6_LV.html`
- **Abgeschlossene Verfahren** (completed): `DE/Beschlusskammern/BK06/BK6_21_AV/BK6_AV.html`,
  which links to one index page per year (2006 → current).

Each proceeding is keyed by **Aktenzeichen** (e.g. `BK6-23-241`) and lives under:

```
/DE/Beschlusskammern/1_GZ/BK6-GZ/{year}/{aktenzeichen}/{aktenzeichen}_{phase}.html
```

A single Aktenzeichen may have **multiple phase pages** (`_konsultation.html`,
`_festlegungsverfahren.html`, …). Each page carries metadata (title, `Stand:` date,
procedural status, submission deadline, background text) and links one or more PDFs named
`{aktenzeichen}_{doctype}.pdf`.

## Package modules (`src/bnetza_bk6_scraper/`)

| Module | Responsibility |
|---|---|
| `models.py` | Pydantic models. `Document`(title, doc_type, source_url, filename). `Proceeding`(aktenzeichen, year, title, stand, status, deadline, pages, documents). |
| `fetch.py` | Async `aiohttp` client wrapper: polite User-Agent, bounded concurrency, retry-with-backoff on transient errors. |
| `discovery.py` | Enumerate proceeding URLs from both index surfaces (laufende + abgeschlossene year pages 2006→current). |
| `parse.py` | BeautifulSoup parsing: index pages → proceeding/page URLs; proceeding pages → metadata + PDF links. |
| `normalize.py` | Strip nav/cookie/analytics chrome; extract main content → stable HTML snapshot for clean diffs. |
| `scraper.py` | `BnetzaBk6Scraper` orchestrator with async `mirror(target_dir)`. |
| `cli.py` | Typer CLI. |

## Crawl & data flow

1. `discovery` collects all proceeding page URLs from both index surfaces.
2. For each proceeding, fetch its page(s); `parse` extracts metadata + PDF links.
   Phase pages sharing an Aktenzeichen are aggregated into one `Proceeding`.
3. Download every linked PDF. **Change detection is dumb**: always download; git in the
   mirror repo detects what actually changed.
4. Write to the mirror, mirroring the site's own path structure:

```
/{year}/{aktenzeichen}/
    metadata.json                    # aggregated structured Proceeding data
    {aktenzeichen}_{phase}.html      # normalized snapshot, one per phase page
    {aktenzeichen}_{doctype}.pdf     # each document
```

5. Write a top-level `index.json` listing all proceedings for downstream consumption.

**Year derivation.** The `laufende Verfahren` index has no year grouping, so `year` is taken
authoritatively from the Aktenzeichen / source URL path (`BK6-23-241` → 2023), not from the
index page a proceeding was discovered on.

**Example `metadata.json`:**

```json
{
  "aktenzeichen": "BK6-23-241",
  "year": 2023,
  "title": "Fortentwicklung des sog. 'Redispatch 2.0'",
  "stand": "2024-09-26",
  "status": "Konsultation",
  "deadline": "2024-11-04",
  "pages": [
    { "phase": "konsultation", "source_url": ".../BK6-23-241_konsultation.html" }
  ],
  "documents": [
    {
      "title": "Konsultationsdokument",
      "doc_type": "konsultationsdokument",
      "source_url": ".../BK6-23-241_konsultationsdokument.pdf",
      "filename": "BK6-23-241_konsultationsdokument.pdf"
    }
  ]
}
```

`index.json` is an array of `{aktenzeichen, year, title, status, stand}` summaries with the
relative path to each proceeding folder.

If two phase pages link a PDF with an identical `{aktenzeichen}_{doctype}.pdf` name, it is
treated as the same document (deduplicated); genuinely distinct documents are expected to
carry distinct doctype suffixes.

## CLI (Typer)

```
bnetza-bk6-scraper mirror --target ./ [--concurrency 4] [--year 2023] [-v]
```

- `--target` (required): output directory (the mirror repo root).
- `--concurrency`: bounded parallel fetches (default 4).
- `--year`: restrict to a single year for fast local testing; default = all.
- `-v/--verbose`: debug logging.

## Error handling

- Polite by default: bounded concurrency + small inter-request delay + retry/backoff on
  transient HTTP/network errors.
- A single failed proceeding or PDF logs a **warning** and the run **continues** — one 404
  must not abort a full mirror.
- A run-end summary reports counts (proceedings seen, documents written, failures).
- Exit non-zero only if an entire index surface fails to load (nothing to mirror).

## Testing

- `pytest` with **recorded HTML fixtures** (real sample index + proceeding pages under
  `unittests/fixtures/`); network mocked via **`aioresponses`** — no live network in CI.
- Unit tests: `parse` (metadata extraction, PDF link discovery, multi-phase aggregation),
  `normalize`, path/filename derivation, models validation.
- Integration test: `mirror()` against mocked responses → assert the on-disk tree and
  `metadata.json` / `index.json` contents.

## Dependencies

Runtime: `aiohttp`, `beautifulsoup4`, `lxml`, `typer`, `pydantic`.
Test: `aioresponses` (added to the template's `tests` optional-dependency group).

## Scope boundaries (YAGNI)

- **BK6 only.** The `1_GZ/BK{n}-GZ/...` structure is shared across chambers, but generalizing
  to BK7/BK8 is out of scope. Code is factored so a later generalization is cheap, but no
  chamber abstraction is built now.
- No smart change detection / caching (explicitly chose dumb download).
- The mirror repo and its Action are documented but not built in this cycle.

## Future work (not in this cycle)

- `bnetza_bk6_mirror` repo: `.github/workflows/mirror.yml` (cron → install → run → commit),
  README explaining the diff-based change tracking.

## Implementation findings (2026-07-03, from recorded fixtures)

Verified against real pages while recording test fixtures; the plan encodes these:

1. **WAF requires a browser User-Agent.** `www.bundesnetzagentur.de` sits behind a Web
   Application Firewall that returns a **200-status block page** ("The requested URL was
   rejected. Your support ID is: …") for bot-like User-Agents. The `Fetcher` must send a
   **browser UA + `Accept`/`Accept-Language` headers**, and must treat the block-marker body
   as a retryable failure (it is not an HTTP error status).
2. **Discovery is two fetches, not per-year crawling.** The *Abgeschlossene Verfahren* landing
   page lists **all 430+ proceedings directly** (years are section headers, not separate index
   pages). So discovery = fetch laufende + abgeschlossene, parse links from both. No per-year
   index pages exist.
3. **`<base href="/">`** on every page: links resolve against the site root, so parsers must
   honor the base href when making URLs absolute.
4. **Proceeding/PDF hrefs carry query strings** (`?nn=…`, `?__blob=publicationFile&v=…`), so
   link filters use "contains `.html`/`.pdf`", never "ends-with".
5. **Title is the `<h2>` in `#content`** (the `<h1>` is the Aktenzeichen). `status` is derived
   from the page **phase** (URL suffix), which is reliable.
6. **`deadline` is best-effort.** On the sampled page the deadline date sits in an unlabeled
   cell, so a label-anchored extraction returns `None`. The field is populated only when a
   date is confidently found next to a Frist/Stellungnahme label; otherwise `null`. This
   revises the earlier "always extract deadline" intent — `metadata.json` may carry
   `"deadline": null`.
