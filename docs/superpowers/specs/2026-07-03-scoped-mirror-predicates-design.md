# Scoped Mirroring via Seed Pages + Document Predicates — Design

**Date:** 2026-07-03
**Status:** Draft (design)
**Repo:** `bnetza_bk6_scraper` (this feature); a follow-up mirror-repo PR wires it up.

## Purpose

Today the scraper mirrors **all** BK6 proceedings (the full Laufende + Abgeschlossene
*Verfahren* index, 430+ proceedings). We want to mirror only a curated subset:

- **Electricity (Strom) market-process frameworks: GPKE, WiM, MaBiS.**
- Within those, only their **Prozessdokumente** (the "Teil 1/2/3/4" process descriptions),
  **Lesefassung** (clean reading version) only, **current + future** valid versions
  (superseded versions are *not* mirrored).
- Plus BNetzA's **PID-Liste** ("Anwendungsübersicht der Prüfidentifikatoren").

The mechanism the user wants: pass a **list of predicate functions** (OR semantics — download
a document if *any* predicate returns `True`) to the scraper. Functions cannot travel through
the CLI, so the mirror repo moves from a bare CLI call to a small **Python driver script**
(the `edi_energy_mirror/download_and_post_process.py` pattern) that defines the seeds +
predicates and calls the scraper's Python API. **The scraper stays generic; all policy
(which pages, which document kinds) lives in the mirror script.**

## Site-structure findings (the crux, verified 2026-07)

These findings drove the design and are recorded so the plan doesn't re-derive them.

1. **GPKE/WiM/MaBiS live on dedicated topic pages, not the Verfahren index.** They sit under
   `DE/Beschlusskammern/BK06/BK6_83_Zug_Mess/` — a separate tree from the
   Laufende/Abgeschlossene *Verfahren* index the scraper crawls today. Examples:
   - GPKE: `BK6_83_Zug_Mess/831_gpke/gpke_node.html`
   - MaKo 2022 (consolidated GPKE/WiM/MPES/MaBiS): `BK6_83_Zug_Mess/8352_mako2022/BK6_mako2022_node.html`
   - MaBiS-Hub: `BK6_83_Zug_Mess/845_MaBiS_Hub/BK6_MaBiS_Hub_node.html`

   Each topic page is a curated clearinghouse with "**Aktuell gültige Fassung**",
   "**Zukünftig gültige Fassung**", and "**Bislang gültige Fassungen**" sections.

2. **The document PDFs point back into `/BK6-GZ/` proceeding URLs.** The current
   GPKE/WiM/MaBiS reading versions all live in one Festlegung proceeding, **`BK6-24-174`**,
   under `/Beschluss/`, with clean, predictable filenames:
   - `BK6-24-174_GPKE_Teil1_Lesefassung.pdf` … `_Teil3_Lesefassung.pdf`
     (`Teil4` is carried over from `BK6-22-024`: `Anlage1d_GPKE_Teil4.pdf`)
   - `BK6-24-174_WiM_Teil1_Lesefassung_korr.pdf`, `BK6-24-174_WiM_Teil2_Lesefassung.pdf`
   - `BK6-24-174_MaBiS_Lesefassung.pdf`
   - Each also exists in an `_Aenderung` (change-tracked) variant, which we **exclude**.
   Crucially, in the topic page's *"Aktuell/Zukünftig gültige Fassung"* sections these PDFs
   are **direct links** — reachable at crawl depth 0–1 without descending into history.

3. **The PID-Liste lives in a different subtree with no Aktenzeichen.** BNetzA publishes the
   "Anwendungsübersicht der Prüfidentifikatoren" under the **Datenformate** notices tree:
   `BK6_83_Zug_Mess/835_mitteilungen_datenformate/Mitteilung_NN/Anlagen/PID_*.pdf`
   (e.g. `PID_3_2_...pdf`). These URLs carry **no** `BK6-YY-NNN` Aktenzeichen, so today's
   Aktenzeichen-keyed layout and discovery cannot represent them.

4. **Aktivitätsdiagramme are BDEW-hosted, out of scope here.** The "BDEW-Anwendungshilfe
   Aktivitätsdiagramme" lives on `bdew.de`, not on BNetzA. They are handled in a **separate
   follow-up feature on `edi_energy_scraper`** (next cycle), not in this scraper.

### Coverage rule that shaped scope

The user's rule: *only exclude a doc kind here if `edi_energy_mirror` already covers it.*
Verified against the `edi_energy_mirror` file tree (1373 PDFs):

| Doc kind | On BNetzA BK6 | In edi_energy_mirror | Decision |
|---|---|---|---|
| GPKE/WiM/MaBiS **Prozessdokumente** | ✅ (`BK6-24-174`) | ❌ | **Mirror here** |
| **PID-Liste** | ✅ (Datenformate tree) | ✅ (`anwendungsbersichtderprfidentifikatoren_*.pdf`, all versions) | **Mirror here anyway** (user wants a BNetzA-sourced copy) |
| **Aktivitätsdiagramme** | ❌ (BDEW only) | ❌ | **Defer** → `edi_energy_scraper` |

## Design overview

Generalize the scraper from *"crawl two fixed indexes, download every PDF"* to
*"crawl a caller-supplied set of seed pages within bounded depth, and download every
discovered PDF that any caller-supplied predicate accepts."* The existing full-index
`mirror(...)` path is **kept unchanged** for back-compat.

```
seeds ─▶ bounded crawler ─▶ CandidateDocument stream ─▶ keep-predicates (OR) ─▶ download + write
```

### New model: `CandidateDocument` (`models.py`)

Carries everything a predicate needs to decide **without downloading first**:

| Field | Type | Notes |
|---|---|---|
| `source_url` | `str` | Absolute PDF URL. |
| `filename` | `str` | Bare filename (as today). |
| `title` | `str` | Anchor link text (falls back to filename). |
| `found_on` | `str` | URL of the page the link was found on — gives topic/framework context. |
| `aktenzeichen` | `str \| None` | Parsed when derivable from the URL path; `None` for PID docs. |
| `doc_type` | `str \| None` | Parsed from the filename after the Aktenzeichen prefix when present, else `None`. |

`Document`/`Proceeding`/`ProceedingPage` are unchanged.

### Discovery: bounded crawler (`discovery.py`)

New async function alongside `discover_proceeding_urls`:

```python
async def crawl_candidates(
    fetcher: Fetcher,
    seeds: list[str],
    max_depth: int = 1,
    url_prefixes: list[str] | None = None,
) -> list[CandidateDocument]:
```

- Breadth-first from `seeds`. For each fetched HTML page: collect `.pdf` anchors into
  `CandidateDocument`s (resolving `<base href>` as the existing parser does), and enqueue
  same-host HTML links **whose URL starts with one of `url_prefixes`** (default: derive an
  allowlist from the seeds' own `…/BK06/` path prefix) for the next depth level, up to
  `max_depth`.
- Visited-URL set prevents re-fetching; candidates deduped by `source_url`.
- **Superseded avoidance:** the default `max_depth=1` plus seeding only the topic pages keeps
  the crawl on the "Aktuell/Zukünftig gültige Fassung" direct links and out of the deeper
  "Bislang gültige Fassungen" tables. Depth is a knob, not a policy — the mirror script picks
  it.
- Reuses the existing WAF-aware browser-UA `Fetcher` and its concurrency semaphore.

### Predicate application (`scraper.py`)

New public method on `BnetzaBk6Scraper`:

```python
async def mirror_seeds(
    self,
    target_dir: str | Path,
    seeds: list[str],
    keep: list[Callable[[CandidateDocument], bool]],
    max_depth: int = 1,
    url_prefixes: list[str] | None = None,
) -> list[CandidateDocument]:
```

- `keep` is a **required** argument (no default) so a caller can never silently mirror
  nothing or everything by omission.
- Crawl → for each `CandidateDocument`, keep it iff **any** predicate in `keep` returns
  `True` (empty `keep` list ⇒ keep nothing; explicit and safe).
- Download kept docs and write them (layout below). Failures are logged and swallowed per
  document, matching the existing run-continues behavior. Emits the same style of run-summary
  log line.
- Returns the list of kept `CandidateDocument`s (for the driver's logging/inspection).

The existing `mirror(...)` and the `mirror` CLI command are untouched.

### Output layout (`scraper.py`)

- **With Aktenzeichen** (all Prozessdokumente — they live in `BK6-24-174` etc.): the
  **existing** `target/<year>/<aktenzeichen>/<filename>` layout. The proceeding page HTML that
  the crawl passed through is normalized and written as today where an Aktenzeichen page is
  fetched, and `metadata.json` is written per proceeding. (Reuse existing helpers; the seed
  path may fetch the proceeding page as part of the crawl, or synthesize minimal metadata from
  the candidate — see Open questions.)
- **Without Aktenzeichen** (PID-Liste): a generic, **policy-free** URL-derived path so the
  scraper hardcodes no topic names:
  `target/_other/<path-after-/BK06/>/<filename>`
  e.g. `target/_other/BK6_83_Zug_Mess/835_mitteilungen_datenformate/Mitteilung_48/Anlagen/PID_3_2_...pdf`.

### CLI

No new CLI surface is required (predicates cannot cross the CLI). The existing `mirror`
command stays. Optionally document that scoped mirroring is a Python-API feature.

## Mirror repo change (separate follow-up PR on `bnetza_bk6_mirror`)

Not part of this repo's PR, documented for context:

- Add `download_and_post_process.py` that:
  - defines `SEEDS` = the GPKE / WiM / MaBiS / MaKo2022 topic-page URLs + the PID source page,
  - defines the predicates below,
  - calls `BnetzaBk6Scraper(...).mirror_seeds(target_dir=".", seeds=SEEDS, keep=[...])`.
- Point `mirror.yml` at the script instead of `bnetza-bk6-scraper mirror --target .`.

Example predicates (policy lives here, not in the package):

```python
def is_prozessdokument_lesefassung(c: CandidateDocument) -> bool:
    name = c.filename.lower()
    return (
        any(fw in name for fw in ("_gpke_", "_wim_", "_mabis_"))
        and "lesefassung" in name
        and "aenderung" not in name
    )

def is_pid_liste(c: CandidateDocument) -> bool:
    name = c.filename.lower()
    return name.startswith("pid_") or "prüfidentifikator" in c.title.lower()
```

## Testing

- Capture fixture HTML from the real GPKE topic page, the `BK6-24-174` proceeding page, and a
  Datenformate/Mitteilung page (small, trimmed to the relevant anchors).
- Unit tests:
  - `crawl_candidates`: depth bounding (depth 0 vs 1), `url_prefixes` allowlist, dedup,
    visited-set (no re-fetch), `<base href>` resolution, candidate field parsing
    (Aktenzeichen present vs `None`).
  - `mirror_seeds`: OR combination of predicates, empty-`keep` ⇒ nothing kept, both layout
    branches (Aktenzeichen vs `_other/`), per-doc failure is swallowed.
  - Example predicates: match GPKE/WiM/MaBiS Lesefassung; reject `_Aenderung`; match PID.
- Fetching is mocked (no live network in tests), consistent with existing tests.
- Keep `tox` green: pylint 10/10, mypy `--strict`, coverage at the repo's bar (~98%).

## Delivery

- Additive change → **minor version bump**. New public API (`mirror_seeds`,
  `crawl_candidates`, `CandidateDocument`); existing API/CLI unchanged.
- One feature branch + PR on `bnetza_bk6_scraper`, cut a release as usual.
- Follow-ups (separate cycles): (a) mirror-repo PR to adopt the driver script; (b)
  `edi_energy_scraper` Aktivitätsdiagramme support.

## Open questions / decisions to confirm in planning

1. **Proceeding metadata for Aktenzeichen docs discovered via crawl.** When a candidate has
   an Aktenzeichen but we reached the PDF via a topic page (not the proceeding's own phase
   page), do we (a) additionally fetch + parse + write the proceeding page HTML + full
   `metadata.json` (richer, more fetches), or (b) write just the PDF plus a minimal
   `metadata.json` synthesized from the candidate? Leaning (b) for simplicity; (a) if we want
   parity with the existing layout. *Recommend deciding in the plan.*
2. **PID "current only".** The current PID PDF is nested one hop below the Datenformate page
   (inside a `Mitteilung_NN`), and multiple `Mitteilung_NN` pages expose different (superseded)
   PID versions. To honor "current only" without a version marker in the filename, the mirror
   script should **seed the specific page/section that links the current PID** and keep
   `max_depth` shallow, rather than crawling all Mitteilungen. Exact seed URL to be pinned in
   the mirror-repo follow-up.
3. **Default `url_prefixes` granularity.** When `url_prefixes` is `None`, derive from each
   seed's own directory (e.g. `…/831_gpke/`) rather than the whole `…/BK06/` subtree, so a
   depth-1 crawl stays local to the seeded topic and does not wander the entire chamber. To
   be confirmed in the plan.
```
