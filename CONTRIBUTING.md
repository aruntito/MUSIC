# Contributing to Music Library Agent

Thank you for your interest in contributing. This document outlines the development workflow, code standards, and contribution process.

## Development Setup

```bash
git clone https://github.com/aruntito/MUSIC.git
cd MUSIC

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running Tests

All contributions must keep the full test suite passing:

```bash
.venv/bin/pytest -v
```

Expected baseline: **112 tests passing, 0 failures**.

## Contribution Guidelines

### What is in scope

- Bug fixes in existing modules
- New artist entries in `config/library_rules.json`
- Performance improvements to the organizer, matcher, or deduplicator
- Additional transport backends for `sync-phone` (e.g. MTP, wireless ADB)
- Improved metadata handling (e.g. cover art, MusicBrainz lookups)
- New CLI flags that do not weaken existing safety guarantees
- Test coverage improvements
- Documentation improvements

### What is NOT in scope

The following will not be accepted as contributions:

- Stream ripping from any streaming service (Spotify, YouTube, Apple Music, etc.)
- DRM circumvention of any kind
- Fuzzy/probabilistic artist matching that could misroute files
- Auto-deletion of source, destination, or phone files
- Any feature that weakens SSRF protection, the domain allowlist, or the download size limit
- Dependencies that phone home or require cloud accounts for basic operation

These are hard design constraints, not negotiable via pull request.

## Pull Request Process

1. Fork the repository and create a branch: `git checkout -b feature/your-feature`
2. Write tests for any new behavior. New modules require a new `tests/test_<module>.py` file.
3. Verify: `.venv/bin/pytest -v` — must show 0 failures.
4. Keep commits focused. One logical change per PR.
5. Write a clear PR description explaining what changed and why.
6. Reference any related issues.

## Code Style

- Python 3.10+ compatible
- Type hints on all public functions
- Docstrings on all modules and public classes
- No external network calls in unit tests — mock all I/O
- No hardcoded user-specific paths in library code (use `config/library_rules.json` for paths)

## Adding Artists

To add artists to the curated list, edit `config/library_rules.json` under the appropriate category (`International`, `Indian/Telugu`, `Indian/Hindi`):

```json
{
  "name": "Artist Name",
  "aliases": ["artist name", "artist alias"]
}
```

Then run `python music_agent_cli.py check-config` to validate and add a corresponding test case in `tests/test_curated_artists.py`.

## Commit Messages

Use conventional commit format:

- `feat: add wireless ADB backend`
- `fix: handle ZIP archives with no audio files`
- `docs: expand README installation section`
- `test: add test for SHA-256 deduplication edge case`
- `chore: update requirements`
