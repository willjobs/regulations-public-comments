"""Tests for CommentsDownloader._get_processed_data."""

from tests.conftest import make_comment_header_item, make_comment_detail_item


def test_basic_comment_header(downloader):
    items = [make_comment_header_item("FDA-2021-N-0270-0002")]
    result = downloader._get_processed_data(items, id_col="commentId")

    assert len(result) == 1
    row = result[0]
    assert row["commentId"] == "FDA-2021-N-0270-0002"
    assert row["agencyId"] == "FDA"
    # Excluded columns should not be present
    assert "id" not in row
    assert "displayProperties" not in row
    assert "highlightedContent" not in row
    assert "fileFormats" not in row


def test_id_is_first_key(downloader):
    items = [make_comment_header_item("FDA-2021-N-0270-0003")]
    result = downloader._get_processed_data(items, id_col="commentId")
    assert list(result[0].keys())[0] == "commentId"


def test_list_value_is_joined(downloader):
    item = {
        "id": "DOC-1",
        "attributes": {
            "keywords": ["environment", "clean air"],
            "lastModifiedDate": "2021-01-01T00:00:00Z",
        },
    }
    result = downloader._get_processed_data([item], id_col="documentId")
    assert result[0]["keywords"] == "environment clean air"


def test_multiple_items(downloader):
    items = [
        make_comment_header_item("FDA-2021-N-0270-0010"),
        make_comment_header_item("FDA-2021-N-0270-0011"),
        make_comment_header_item("FDA-2021-N-0270-0012"),
    ]
    result = downloader._get_processed_data(items, id_col="commentId")
    assert len(result) == 3
    assert [r["commentId"] for r in result] == [
        "FDA-2021-N-0270-0010",
        "FDA-2021-N-0270-0011",
        "FDA-2021-N-0270-0012",
    ]


def test_attachments_are_joined_with_pipe(downloader):
    items = [make_comment_detail_item("FDA-2021-N-0270-0020")]
    attachments = [
        [
            {"fileUrl": "https://downloads.regulations.gov/file1.pdf", "format": "pdf", "size": 12345},
            {"fileUrl": "https://downloads.regulations.gov/file2.pdf", "format": "pdf", "size": 67890},
        ]
    ]
    result = downloader._get_processed_data(items, id_col="commentId", attachments=attachments)
    assert result[0]["attachmentLinks"] == (
        "https://downloads.regulations.gov/file1.pdf"
        "|https://downloads.regulations.gov/file2.pdf"
    )


def test_no_attachments_gives_empty_string(downloader):
    items = [make_comment_detail_item("FDA-2021-N-0270-0021")]
    attachments = [None]
    result = downloader._get_processed_data(items, id_col="commentId", attachments=attachments)
    assert result[0]["attachmentLinks"] == ""


def test_attachments_none_argument_not_added(downloader):
    items = [make_comment_detail_item("FDA-2021-N-0270-0022")]
    result = downloader._get_processed_data(items, id_col="commentId", attachments=None)
    assert "attachmentLinks" not in result[0]
