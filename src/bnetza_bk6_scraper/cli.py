"""Command-line interface for the BK6 scraper."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer

from bnetza_bk6_scraper.scraper import BnetzaBk6Scraper

app = typer.Typer(help="Mirror Bundesnetzagentur Beschlusskammer 6 documents.")


@app.callback()
def main() -> None:
    """Command-line entry point for the BK6 scraper."""


@app.command()
def mirror(
    target: Path = typer.Option(..., "--target", help="Output directory (mirror repo root)."),
    concurrency: int = typer.Option(4, "--concurrency", help="Parallel fetches."),
    year: Optional[int] = typer.Option(None, "--year", help="Restrict to a single year."),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Debug logging."),
) -> None:
    """Download BK6 proceedings into TARGET as a structured, diffable tree."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO)
    scraper = BnetzaBk6Scraper(concurrency=concurrency)
    asyncio.run(scraper.mirror(target, year=year))


if __name__ == "__main__":
    app()
