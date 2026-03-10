"""Tests for the CLI entry point (cli.py)."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from regulations_public_comments.cli import main


@pytest.fixture()
def runner():
    return CliRunner()


def test_help_exits_zero(runner):
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--key" in result.output
    assert "--docket" in result.output
    assert "--document" in result.output


def test_missing_key_shows_error(runner):
    result = runner.invoke(main, ["--docket", "FDA-2021-N-0270"])
    assert result.exit_code != 0
    assert "key" in result.output.lower() or "Missing option" in result.output


def test_missing_target_shows_error(runner):
    result = runner.invoke(main, ["--key", "DEMO_KEY"])
    assert result.exit_code != 0


def test_docket_calls_gather_comments_by_docket(runner):
    mock_downloader = MagicMock()
    with patch(
        "regulations_public_comments.cli.CommentsDownloader",
        return_value=mock_downloader,
    ):
        result = runner.invoke(main, ["--key", "DEMO_KEY", "--docket", "FDA-2021-N-0270"])

    assert result.exit_code == 0
    mock_downloader.gather_comments_by_docket.assert_called_once_with(
        "FDA-2021-N-0270", csv_filename="FDA-2021-N-0270.csv"
    )


def test_document_calls_gather_comments_by_document(runner):
    mock_downloader = MagicMock()
    with patch(
        "regulations_public_comments.cli.CommentsDownloader",
        return_value=mock_downloader,
    ):
        result = runner.invoke(main, ["--key", "DEMO_KEY", "--document", "FDA-2009-N-0501-0012"])

    assert result.exit_code == 0
    mock_downloader.gather_comments_by_document.assert_called_once_with(
        "FDA-2009-N-0501-0012", csv_filename="FDA-2009-N-0501-0012.csv"
    )


def test_api_key_passed_to_downloader(runner):
    mock_downloader = MagicMock()
    with patch(
        "regulations_public_comments.cli.CommentsDownloader",
        return_value=mock_downloader,
    ) as MockDownloader:
        runner.invoke(main, ["--key", "MY_SECRET_KEY", "--docket", "FDA-2021-N-0270"])

    MockDownloader.assert_called_once_with(api_key="MY_SECRET_KEY")
