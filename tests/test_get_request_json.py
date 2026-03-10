"""Tests for CommentsDownloader.get_request_json (HTTP layer, mocked)."""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_comment_header_item, make_duplicate_server_error, make_list_response

BASE_URL = "https://api.regulations.gov/v4/comments"


def _make_mock_response(status_code, json_data, headers=None):
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.headers = {"X-RateLimit-Remaining": "900", **(headers or {})}
    return mock_resp


def test_successful_request_returns_json(downloader):
    payload = make_list_response([make_comment_header_item("FDA-001")])
    mock_resp = _make_mock_response(200, payload)

    with patch("regulations_public_comments.downloader.requests.Session") as MockSession:
        MockSession.return_value.get.return_value = mock_resp
        result = downloader.get_request_json(BASE_URL, params={})

    assert result == payload


def test_page_size_added_for_collection_endpoints(downloader):
    payload = make_list_response([])
    mock_resp = _make_mock_response(200, payload)

    with patch("regulations_public_comments.downloader.requests.Session") as MockSession:
        mock_get = MockSession.return_value.get
        mock_get.return_value = mock_resp
        downloader.get_request_json(BASE_URL, params={"filter[agencyId]": "FDA"})

    _, kwargs = mock_get.call_args
    assert kwargs["params"]["page[size]"] == 250


def test_page_size_not_added_for_detail_endpoints(downloader):
    """Detail endpoints like /comments/FDA-001 should NOT get page[size]."""
    detail_url = "https://api.regulations.gov/v4/comments/FDA-001"
    payload = {"data": make_comment_header_item("FDA-001")}
    mock_resp = _make_mock_response(200, payload)

    with patch("regulations_public_comments.downloader.requests.Session") as MockSession:
        mock_get = MockSession.return_value.get
        mock_get.return_value = mock_resp
        downloader.get_request_json(detail_url, params={})

    _, kwargs = mock_get.call_args
    assert "page[size]" not in kwargs["params"]


def test_non_200_raises(downloader):
    mock_resp = _make_mock_response(403, {"errors": [{"status": "403", "detail": "Forbidden"}]})
    mock_resp.raise_for_status.side_effect = Exception("403 Forbidden")

    with patch("regulations_public_comments.downloader.requests.Session") as MockSession:
        MockSession.return_value.get.return_value = mock_resp
        with pytest.raises(Exception, match="403 Forbidden"):
            downloader.get_request_json(BASE_URL, params={}, wait_for_rate_limits=False)


def test_duplicate_server_error_skipped_when_skip_duplicates(downloader):
    error_payload = make_duplicate_server_error()
    mock_resp = _make_mock_response(500, error_payload)

    with patch("regulations_public_comments.downloader.requests.Session") as MockSession:
        MockSession.return_value.get.return_value = mock_resp
        result = downloader.get_request_json(BASE_URL, params={}, skip_duplicates=True)

    # Should return the error JSON without raising
    assert "errors" in result
