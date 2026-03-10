"""Tests for CommentsDownloader._is_duplicated_on_server."""

from tests.conftest import make_duplicate_server_error


def test_is_duplicated_returns_true_for_known_error(downloader):
    response = make_duplicate_server_error()
    assert downloader._is_duplicated_on_server(response) is True


def test_is_duplicated_returns_false_for_success_response(downloader):
    response = {"data": {"id": "ABC-1234", "attributes": {}}}
    assert downloader._is_duplicated_on_server(response) is False


def test_is_duplicated_returns_false_for_other_error(downloader):
    response = {
        "errors": [
            {
                "status": "404",
                "title": "Not Found",
                "detail": "The item you requested was not found.",
            }
        ]
    }
    assert downloader._is_duplicated_on_server(response) is False


def test_is_duplicated_returns_false_when_detail_does_not_match(downloader):
    response = {
        "errors": [
            {
                "status": "500",
                "title": "Internal Server Error",
                "detail": "Some other server error",
            }
        ]
    }
    assert downloader._is_duplicated_on_server(response) is False


def test_is_duplicated_returns_false_for_empty_dict(downloader):
    assert downloader._is_duplicated_on_server({}) is False
