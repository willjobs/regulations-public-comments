# Programmatic API

## Understanding the two API tiers

The Regulations.gov API has two main tiers:

- **Headers** (`/v4/comments`, `/v4/documents`, `/v4/dockets`) — bulk search, returns a small set of fields per item
- **Details** (`/v4/comments/{id}`) — single-item lookup, returns all fields including the full comment text

`gather_comments_by_docket` and `gather_comments_by_document` automatically call both tiers for you. For custom queries, you can call them separately.

## Low-level access

Use `get_request_json` to get the raw API response for any endpoint:

```python
# Get details for a specific comment
r = downloader.get_request_json(
    "https://api.regulations.gov/v4/comments/FDA-2021-N-0270-0023"
)
print(r["data"]["attributes"]["comment"])

# Custom search with filters
r = downloader.get_request_json(
    "https://api.regulations.gov/v4/comments",
    params={
        "filter[agencyId]": "EPA",
        "filter[postedDate][ge]": "2023-06-01",
        "sort": "postedDate",
    },
)
print(f"Found {r['meta']['totalElements']} comments")
```

## Handling multiple dockets

```python
docket_ids = ["FDA-2021-N-0270", "EERE-2019-BT-STD-0036", "NHTSA-2019-0121"]

for docket_id in docket_ids:
    downloader.gather_comments_by_docket(
        docket_id,
        db_filename="all_comments.db",
        csv_filename=f"{docket_id}.csv",
    )
```

## Querying the resulting database

```python
import sqlite3
import pandas as pd

conn = sqlite3.connect("all_comments.db")
df = pd.read_sql_query(
    "SELECT commentId, firstName, lastName, comment FROM comments_detail WHERE docketId = ?",
    conn,
    params=("FDA-2021-N-0270",),
)
conn.close()
print(df.head())
```
