"""Tests for database setup and insert operations."""

import sqlite3

import pytest

from regulations_public_comments import CommentsDownloader


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test.db")


def test_setup_database_creates_six_tables(downloader, db_path):
    downloader._setup_database(db_path)
    conn = sqlite3.connect(db_path)
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    expected = {
        "dockets_header",
        "dockets_detail",
        "documents_header",
        "documents_detail",
        "comments_header",
        "comments_detail",
    }
    assert expected == tables


def test_setup_database_idempotent(downloader, db_path):
    """Calling _setup_database twice on the same file should not raise."""
    downloader._setup_database(db_path)
    downloader._setup_database(db_path)


def test_get_database_connection_returns_connection(downloader, db_path):
    conn = downloader._get_database_connection(db_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_insert_data_adds_rows(downloader, db_path):
    conn = downloader._get_database_connection(db_path)
    cur = conn.cursor()

    data = [
        {
            "docketId": "FDA-2021-N-0270",
            "agencyId": "FDA",
            "docketType": "Rulemaking",
            "title": "Test Docket",
            "lastModifiedDate": "2021-01-01T00:00:00Z",
            "objectId": "0900006483abc123",
        }
    ]
    downloader._insert_data(data, "dockets_header", conn, cur)

    count = cur.execute("SELECT count(*) FROM dockets_header").fetchone()[0]
    conn.close()
    assert count == 1


def test_insert_data_ignores_duplicates(downloader, db_path):
    """Inserting the same docketId twice should result in only one row (UNIQUE constraint)."""
    conn = downloader._get_database_connection(db_path)
    cur = conn.cursor()

    row = {
        "docketId": "FDA-2021-N-0270",
        "agencyId": "FDA",
        "docketType": "Rulemaking",
        "title": "Test Docket",
        "lastModifiedDate": "2021-01-01T00:00:00Z",
        "objectId": "0900006483abc123",
    }
    downloader._insert_data([row], "dockets_header", conn, cur)
    downloader._insert_data([row], "dockets_header", conn, cur)

    count = cur.execute("SELECT count(*) FROM dockets_header").fetchone()[0]
    conn.close()
    assert count == 1


def test_drop_if_exists_clears_tables(downloader, db_path):
    conn = downloader._get_database_connection(db_path)
    cur = conn.cursor()
    row = {
        "docketId": "FDA-2021-N-0270",
        "agencyId": "FDA",
        "docketType": "Rulemaking",
        "title": "Test Docket",
        "lastModifiedDate": "2021-01-01T00:00:00Z",
        "objectId": "0900006483abc123",
    }
    downloader._insert_data([row], "dockets_header", conn, cur)
    conn.close()

    # Re-setup with drop
    downloader._setup_database(db_path, drop_if_exists=True)
    conn2 = sqlite3.connect(db_path)
    count = conn2.execute("SELECT count(*) FROM dockets_header").fetchone()[0]
    conn2.close()
    assert count == 0
