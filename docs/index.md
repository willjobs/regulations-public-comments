# regulations-public-comments

A Python wrapper for the [Regulations.gov API](https://open.gsa.gov/api/regulationsgov/) that makes it easy to download public comments, dockets, and documents.

## Key features

- **Simple high-level API** — download all comments for a docket or document with one function call
- **Automatic pagination** — handles the API's 5,000-record-per-query limit transparently
- **Rate limit handling** — automatically waits and retries when the hourly limit is hit
- **Flexible output** — save to CSV, SQLite, or both
- **CLI included** — the `comments-downloader` command works out of the box after installation

## Quick example

```python
from regulations_public_comments import CommentsDownloader

downloader = CommentsDownloader(api_key="YOUR_API_KEY")

# Download all comments for an FDA docket into a CSV
downloader.gather_comments_by_docket("FDA-2021-N-0270", csv_filename="fda_comments.csv")
```

Or from the command line:

```bash
comments-downloader --key YOUR_API_KEY --docket FDA-2021-N-0270
```

## Getting started

- [Installation](installation.md) — how to install with pip or uv
- [Quick Start](usage/quickstart.md) — the most common use cases
- [API Reference](api.md) — full documentation of every method
