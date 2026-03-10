# Quick Start

## Command-line usage

After installation, the `comments-downloader` command is available:

```bash
# Download all comments for a docket (saves to FDA-2021-N-0270.csv)
comments-downloader --key YOUR_API_KEY --docket FDA-2021-N-0270

# Download all comments for a specific document (saves to FDA-2009-N-0501-0012.csv)
comments-downloader --key YOUR_API_KEY --document FDA-2009-N-0501-0012
```

Run `comments-downloader --help` for full usage information.

## Python API — basic usage

```python
from regulations_public_comments import CommentsDownloader

downloader = CommentsDownloader(api_key="YOUR_API_KEY")

# Download all comments for a docket into a CSV
downloader.gather_comments_by_docket("FDA-2021-N-0270", csv_filename="fda_comments.csv")

# Download all comments for a specific document
downloader.gather_comments_by_document("FDA-2009-N-0501-0012", csv_filename="doc_comments.csv")

# Save to a SQLite database instead
downloader.gather_comments_by_docket("FDA-2021-N-0270", db_filename="regulations.db")

# Save to both
downloader.gather_comments_by_docket(
    "FDA-2021-N-0270",
    db_filename="regulations.db",
    csv_filename="fda_comments.csv",
)
```

## Checking API request limits

```python
remaining = downloader.get_requests_remaining()
print(f"Requests remaining this hour: {remaining}")
```

## Counting results before downloading

```python
count = downloader.get_items_count(
    "comments",
    params={"filter[agencyId]": "EPA", "filter[postedDate][ge]": "2023-01-01"},
)
print(f"EPA comments since 2023: {count}")
```

## Downloading headers for a custom query

```python
downloader.gather_headers(
    data_type="comments",
    params={"filter[agencyId]": "EPA", "filter[postedDate][ge]": "2023-01-01"},
    csv_filename="epa_2023_headers.csv",
)
```

## Downloading detail records

```python
# First get IDs from a headers CSV, then fetch full details
comment_ids = downloader.get_ids_from_csv("epa_2023_headers.csv", "comments", unique=True)
downloader.gather_details("comments", comment_ids, csv_filename="epa_2023_details.csv")
```

For more examples, see [Examples.ipynb](https://github.com/willjobs/regulations-public-comments/blob/master/Examples.ipynb).
