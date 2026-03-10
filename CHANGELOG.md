# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2024-01-01

### Added
- Packaged as a proper Python package (`regulations-public-comments`) installable via `pip` and `uv`
- CLI entry point `comments-downloader` registered via `pyproject.toml`; no longer requires running `python comments_downloader.py` directly
- `rich-click`-powered CLI with colored, grouped `--help` output and usage examples
- Test suite using `pytest` with mocked HTTP — no API key required to run tests
- MkDocs documentation site with Material theme, auto-generated API reference, deployed to GitHub Pages
- GitHub Actions CI: runs tests on Python 3.9, 3.10, 3.11, 3.12 on every push and pull request
- GitHub Actions docs deploy: publishes MkDocs site to GitHub Pages on pushes to `master`
- `CONTRIBUTING.md` with dev setup and release instructions
- `uv.lock` for reproducible development environments

### Changed
- Source moved to `src/regulations_public_comments/` package layout
- Import path updated: `from regulations_public_comments import CommentsDownloader`
  (previously `from comments_downloader import CommentsDownloader`)

## [1.x] - Prior releases

The library was previously distributed as a single file (`comments_downloader.py`) without a formal
package structure or version history. See the git log for the full history.
