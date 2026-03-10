# Installation

Requires Python 3.9+.

## Using uv (recommended)

```bash
uv add regulations-public-comments
```

## Using pip

```bash
pip install regulations-public-comments
```

## Getting an API key

The Regulations.gov API requires a free API key. Sign up at:
[https://open.gsa.gov/api/regulationsgov/#getting-started](https://open.gsa.gov/api/regulationsgov/#getting-started)

Your key gives you **1,000 requests per hour**. The library automatically handles rate limiting — if you hit the limit, it waits and retries.

## Development install

To install from source with dev dependencies:

```bash
git clone https://github.com/willjobs/regulations-public-comments.git
cd regulations-public-comments

# Using uv
uv sync --all-extras

# Using pip
pip install -e ".[dev]"
```
