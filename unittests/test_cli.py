"""Tests for the Typer command-line interface."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

from typer.testing import CliRunner

from bnetza_bk6_scraper.cli import app

runner = CliRunner()


def test_mirror_command_invokes_scraper(tmp_path: Path) -> None:
    """The mirror command constructs the scraper and awaits mirror()."""
    with patch("bnetza_bk6_scraper.cli.BnetzaBk6Scraper") as scraper_cls:
        scraper_cls.return_value.mirror = AsyncMock(return_value=[])
        result = runner.invoke(app, ["mirror", "--target", str(tmp_path), "--concurrency", "2"])
    assert result.exit_code == 0
    scraper_cls.return_value.mirror.assert_awaited_once()
