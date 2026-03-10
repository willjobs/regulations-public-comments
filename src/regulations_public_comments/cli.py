import sys

import rich_click as click

from regulations_public_comments import CommentsDownloader

click.rich_click.TEXT_MARKUP = "rich"
click.rich_click.OPTION_GROUPS = {
    "comments-downloader": [
        {
            "name": "Required",
            "options": ["--key"],
        },
        {
            "name": "Target (one required)",
            "options": ["--docket", "--document"],
        },
        {
            "name": "Other",
            "options": ["--help"],
        },
    ]
}
click.rich_click.EPILOG = (
    "Examples:\n\n"
    "  [bold]# Download all comments for a docket[/bold]\n"
    "  comments-downloader --key DEMO_KEY --docket FDA-2021-N-0270\n\n"
    "  [bold]# Download all comments for a specific document[/bold]\n"
    "  comments-downloader --key DEMO_KEY --document FDA-2009-N-0501-0012\n\n"
    "Get a free API key at: [link=https://open.gsa.gov/api/regulationsgov/]https://open.gsa.gov/api/regulationsgov/[/link]"
)


@click.command()
@click.option(
    "--key",
    required=True,
    metavar="API_KEY",
    help="Your Regulations.gov API key. Get one free at https://open.gsa.gov/api/regulationsgov/",
)
@click.option(
    "--docket",
    default=None,
    metavar="DOCKET_ID",
    help=(
        "Download all comments for this docket ID "
        "(e.g., [bold]FDA-2021-N-0270[/bold], [bold]EERE-2019-BT-STD-0036[/bold]). "
        "Output is saved to [bold]<DOCKET_ID>.csv[/bold] in the current directory."
    ),
)
@click.option(
    "--document",
    default=None,
    metavar="DOCUMENT_ID",
    help=(
        "Download all comments for this document ID "
        "(e.g., [bold]FDA-2009-N-0501-0012[/bold]). "
        "Output is saved to [bold]<DOCUMENT_ID>.csv[/bold] in the current directory."
    ),
)
def main(key, docket, document):
    """Download public comments from Regulations.gov into a CSV file.

    Automatically handles API pagination and rate limiting, so queries that return
    more than 5,000 results (the per-query limit) still work correctly.
    """
    if docket is None and document is None:
        click.echo(
            click.style("Error: ", fg="red", bold=True)
            + "Must specify either --docket or --document. Run with --help for usage."
        )
        sys.exit(1)

    downloader = CommentsDownloader(api_key=key)

    if docket is not None:
        click.echo(f"Downloading comments for docket ID {docket}...")
        downloader.gather_comments_by_docket(docket, csv_filename=f"{docket}.csv")
    else:
        click.echo(f"Downloading comments for document ID {document}...")
        downloader.gather_comments_by_document(document, csv_filename=f"{document}.csv")
