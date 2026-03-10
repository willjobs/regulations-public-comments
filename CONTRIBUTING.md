# Contributing

## Dev setup

Clone and install in editable mode with all dev dependencies:

```bash
git clone https://github.com/willjobs/regulations-public-comments.git
cd regulations-public-comments

# Using uv (recommended)
uv sync --all-extras

# Using pip
pip install -e ".[dev]"
```

## Running the tests

The test suite mocks all HTTP calls — no live API key is needed.

```bash
pytest
```

To run a specific file:

```bash
pytest tests/test_cli.py -v
```

## Generating a requirements.txt (for non-uv users)

If you need a pinned `requirements.txt` for reproducibility without uv:

```bash
uv export --format requirements-txt > requirements.txt
```

## Code style

This project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting.

```bash
# Check for issues
ruff check src/ tests/

# Auto-fix
ruff check --fix src/ tests/

# Format
ruff format src/ tests/
```

## Building the docs locally

```bash
mkdocs serve
```

Then open http://127.0.0.1:8000 in your browser.

## Releasing a new version

1. Update `__version__` in `src/regulations_public_comments/__init__.py`
2. Update `version` in `pyproject.toml`
3. Add a new entry to `CHANGELOG.md`
4. Commit, tag, and push:

   ```bash
   git tag v2.x.x
   git push origin v2.x.x
   ```
