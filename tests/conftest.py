"""Shared fixtures and mock API response data for the test suite."""

import pytest

from regulations_public_comments import CommentsDownloader

# ---------------------------------------------------------------------------
# Helpers: minimal API response shapes
# ---------------------------------------------------------------------------

def make_comment_header_item(comment_id, last_modified="2021-05-01T12:00:00Z"):
    """Return a minimal item dict as returned by the /comments list endpoint."""
    return {
        "id": comment_id,
        "type": "comments",
        "attributes": {
            "agencyId": "FDA",
            "documentType": "Public Submission",
            "lastModifiedDate": last_modified,
            "objectId": f"090000648{comment_id[-4:]}",
            "postedDate": "2021-04-30T04:00:00Z",
            "title": "Comment on FDA regulation",
            "withdrawn": False,
        },
    }


def make_comment_detail_item(comment_id):
    """Return a minimal item dict as returned by the /comments/{id} details endpoint."""
    return {
        "id": comment_id,
        "type": "comments",
        "attributes": {
            "agencyId": "FDA",
            "category": None,
            "city": "Springfield",
            "comment": "This is my public comment text.",
            "commentOn": None,
            "commentOnDocumentId": "FDA-2021-N-0270-0001",
            "country": "United States",
            "docAbstract": None,
            "docketId": "FDA-2021-N-0270",
            "documentType": "Public Submission",
            "duplicateComments": 0,
            "field1": None,
            "field2": None,
            "firstName": "Jane",
            "govAgency": None,
            "govAgencyType": None,
            "lastName": "Doe",
            "legacyId": None,
            "modifyDate": "2021-04-30T12:00:00Z",
            "objectId": f"09000064{comment_id[-4:]}",
            "openForComment": False,
            "organization": None,
            "originalDocumentId": None,
            "pageCount": None,
            "postedDate": "2021-04-30T04:00:00Z",
            "postmarkDate": None,
            "reasonWithdrawn": None,
            "receiveDate": None,
            "restrictReason": None,
            "restrictReasonType": None,
            "stateProvinceRegion": "IL",
            "submitterRep": None,
            "submitterRepCityState": None,
            "subtype": None,
            "title": "Comment on FDA regulation",
            "trackingNbr": "abc123",
            "withdrawn": False,
            "zip": "62701",
        },
    }


def make_list_response(items, total_elements=None, last_page=True):
    """Wrap items in the API's list response envelope."""
    return {
        "data": items,
        "meta": {
            "totalElements": total_elements if total_elements is not None else len(items),
            "pageNumber": 1,
            "pageSize": 250,
            "lastPage": last_page,
        },
    }


def make_detail_response(item, included=None):
    """Wrap a single item in the API's detail response envelope."""
    resp = {"data": item}
    if included is not None:
        resp["included"] = included
    return resp


def make_duplicate_server_error():
    """Return the error JSON the server emits for a duplicated-on-server item."""
    return {
        "errors": [
            {
                "status": "500",
                "title": "Internal Server Error",
                "detail": "Incorrect result size: expected 1, actual 2",
            }
        ]
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def downloader():
    """A CommentsDownloader configured with a dummy API key."""
    return CommentsDownloader(api_key="DEMO_KEY")
