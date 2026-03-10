"""Tests for CSV utility methods: get_ids_from_csv and _remove_duplicates_from_csv."""

import csv

import pytest


def write_csv(path, rows, headers):
    """Helper: write a CSV file with the given headers and rows."""
    with open(path, "w", newline="", encoding="utf8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(headers)
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# get_ids_from_csv
# ---------------------------------------------------------------------------

def test_get_ids_returns_all_ids(downloader, tmp_path):
    csv_file = tmp_path / "comments.csv"
    write_csv(
        csv_file,
        [["FDA-001", "FDA", "Public Submission"], ["FDA-002", "FDA", "Public Submission"]],
        ["commentId", "agencyId", "documentType"],
    )
    ids = downloader.get_ids_from_csv(str(csv_file), "comments")
    assert ids == ["FDA-001", "FDA-002"]


def test_get_ids_unique(downloader, tmp_path):
    csv_file = tmp_path / "comments.csv"
    write_csv(
        csv_file,
        [["FDA-001", "FDA"], ["FDA-001", "FDA"], ["FDA-002", "FDA"]],
        ["commentId", "agencyId"],
    )
    ids = downloader.get_ids_from_csv(str(csv_file), "comments", unique=True)
    assert ids == ["FDA-001", "FDA-002"]


def test_get_ids_non_unique_preserves_duplicates(downloader, tmp_path):
    csv_file = tmp_path / "comments.csv"
    write_csv(
        csv_file,
        [["FDA-001", "FDA"], ["FDA-001", "FDA"]],
        ["commentId", "agencyId"],
    )
    ids = downloader.get_ids_from_csv(str(csv_file), "comments", unique=False)
    assert ids == ["FDA-001", "FDA-001"]


def test_get_ids_singular_data_type(downloader, tmp_path):
    csv_file = tmp_path / "dockets.csv"
    write_csv(csv_file, [["DOC-001"]], ["docketId"])
    ids = downloader.get_ids_from_csv(str(csv_file), "docket")
    assert ids == ["DOC-001"]


def test_get_ids_raises_on_missing_id_column(downloader, tmp_path):
    csv_file = tmp_path / "bad.csv"
    write_csv(csv_file, [["row1"]], ["someOtherColumn"])
    with pytest.raises(ValueError, match="Missing id column"):
        downloader.get_ids_from_csv(str(csv_file), "comments")


# ---------------------------------------------------------------------------
# _remove_duplicates_from_csv
# ---------------------------------------------------------------------------

def test_remove_duplicates_removes_repeated_ids(downloader, tmp_path):
    csv_file = tmp_path / "comments.csv"
    write_csv(
        csv_file,
        [
            ["FDA-001", "Comment A"],
            ["FDA-002", "Comment B"],
            ["FDA-001", "Comment A (dup)"],
        ],
        ["commentId", "comment"],
    )
    downloader._remove_duplicates_from_csv("comments", str(csv_file))

    with open(csv_file, encoding="utf8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    # header + 2 unique rows
    assert len(rows) == 3
    ids = [r[0] for r in rows[1:]]
    assert ids == ["FDA-001", "FDA-002"]


def test_remove_duplicates_noop_when_no_duplicates(downloader, tmp_path):
    csv_file = tmp_path / "comments.csv"
    write_csv(
        csv_file,
        [["FDA-001", "Comment A"], ["FDA-002", "Comment B"]],
        ["commentId", "comment"],
    )
    downloader._remove_duplicates_from_csv("comments", str(csv_file))

    with open(csv_file, encoding="utf8") as f:
        rows = list(csv.reader(f))

    assert len(rows) == 3  # header + 2 rows


def test_remove_duplicates_noop_when_csv_does_not_exist(downloader, tmp_path):
    # Should not raise even if the file doesn't exist yet
    missing = str(tmp_path / "nonexistent.csv")
    downloader._remove_duplicates_from_csv("comments", missing)  # no exception


def test_remove_duplicates_noop_when_csv_filename_is_none(downloader):
    downloader._remove_duplicates_from_csv("comments", None)  # no exception
