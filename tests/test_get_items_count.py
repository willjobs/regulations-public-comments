"""Tests for CommentsDownloader.get_items_count."""

from unittest.mock import patch

from tests.conftest import make_comment_header_item, make_list_response


def test_returns_total_elements(downloader):
    mock_response = make_list_response(
        items=[make_comment_header_item("FDA-2021-N-0270-0001")],
        total_elements=42,
    )
    with patch.object(downloader, "get_request_json", return_value=mock_response):
        count = downloader.get_items_count("comments", params={})
    assert count == 42


def test_plural_normalization(downloader):
    """Singular 'comment' should be treated the same as plural 'comments'."""
    mock_response = make_list_response(items=[], total_elements=7)
    with patch.object(downloader, "get_request_json", return_value=mock_response) as mock_fn:
        downloader.get_items_count("comment", params={})
    # The URL passed should use the pluralized form
    called_endpoint = mock_fn.call_args[0][0]
    assert called_endpoint.endswith("/comments")


def test_zero_results(downloader):
    mock_response = make_list_response(items=[], total_elements=0)
    with patch.object(downloader, "get_request_json", return_value=mock_response):
        count = downloader.get_items_count("dockets", params={})
    assert count == 0
