# bnetza_bk6_scraper

`bnetza_bk6_scraper` mirrors the documents published by the German
Bundesnetzagentur (BNetzA) **Beschlusskammer 6** (BK6) into a structured,
git-diffable directory tree. BK6 regulates electricity network access and is a
constant source of consultations, rulings (Festlegungen) and their attachments.
Because the agency publishes these as loose PDFs on HTML pages with no changelog,
tracking *what* changed and *when* is painful. This tool discovers every BK6
proceeding, downloads its PDFs and a normalized HTML snapshot of each phase page,
and records structured metadata. Committing the output to git turns every
regulatory update into a reviewable diff.

## Installation

```bash
pip install bnetza_bk6_scraper
```

## Usage

The package installs a single console command, `bnetza-bk6-scraper`, with a
`mirror` subcommand:

```bash
bnetza-bk6-scraper mirror --target <dir> [--concurrency N] [--year YYYY] [-v]
```

| Option          | Default | Description                                        |
| --------------- | ------- | -------------------------------------------------- |
| `--target`      | *(required)* | Output directory (the mirror repository root). |
| `--concurrency` | `4`     | Number of parallel HTTP fetches.                   |
| `--year`        | *(all)* | Restrict the run to a single year, e.g. `2023`.    |
| `-v`, `--verbose` | off   | Enable debug logging.                              |

Example — mirror only the 2023 proceedings into `./mirror`:

```bash
bnetza-bk6-scraper mirror --target ./mirror --year 2023 -v
```

Each run logs a summary such as
`run summary: 7 proceedings, 16 documents written, 0 failures`.

## Output layout

Proceedings are written under `/{year}/{aktenzeichen}/`, with a top-level
`index.json` listing every mirrored proceeding:

```text
<target>/
├── index.json                          # summary of all proceedings
└── 2023/
    └── BK6-23-241/
        ├── metadata.json               # structured proceeding metadata
        ├── BK6-23-241_beschluss.html   # normalized HTML snapshot of a phase page
        ├── BK6-23-241_beschluss_vom_07.05.26.pdf
        ├── BK6-23-241_bilarem.pdf
        └── BK6-23-241_anlage_bilarem.pdf
```

- `metadata.json` captures the Aktenzeichen, year, title, status, `Stand`
  (last-modified date), any submission deadline (Frist), the phase pages, and
  one entry per document (title, type, source URL, filename).
- The normalized `*.html` files are trimmed, stable snapshots of the source
  phase pages so that content changes surface as small diffs.
- The PDFs are the proceeding's documents, downloaded verbatim.

Change detection is intentionally "dumb": the tool always writes the current
state, and `git diff` in the mirror repository reveals what changed.

## Mirror repository

The scraper is designed to feed a separate mirror repository,
`Hochfrequenz/bnetza_bk6_mirror`. A scheduled GitHub Action there will
periodically:

```bash
pip install bnetza_bk6_scraper
bnetza-bk6-scraper mirror --target .
git add -A && git commit -m "update BK6 mirror"
```

so that regulatory changes at BK6 become visible as reviewable git diffs and
commit history. That Action is future work and does not live in this repository.

## WAF / browser User-Agent

The BNetzA website sits behind a Web Application Firewall that rejects
non-browser clients by serving a `200 OK` "The requested URL was rejected" page
instead of the real content. To get through, the scraper sends browser-like
`User-Agent` and `Accept` headers and treats the rejection page as a retryable
error. No credentials or API keys are required.

## Contribute

This project uses [tox](https://tox.wiki) for all quality gates. Create a
one-shot development environment with everything installed:

```bash
tox -e dev
```

Individual gates: `tox -e tests`, `tox -e linting`, `tox -e type_check`,
`tox -e coverage`, and `tox -e spell_check`. Run the full suite with `tox`.
