# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] - 2026-08-30

### Added
- **Metadata Enrichment (MusicBrainz)** (`music_agent/enricher.py`):
  - Online metadata enrichment via MusicBrainz recording lookups.
  - Caches queries locally at `~/.cache/music-agent/mb_cache.json`.
  - Rate-limited to 1 request/second adhering to MusicBrainz API terms.
  - **Offline by default**: only invoked with the explicit `--enrich` flag.
- **Album Artwork Management** (`music_agent/artwork.py`):
  - Cover Art Archive resolution for front cover artwork.
  - Dual delivery mode: embeds JPEG into audio tags (`MP3`, `M4A`, `FLAC`, `OGG`) and/or saves `folder.jpg`.
  - No audio re-encoding — tag writes only.
- **Smart M3U8 Playlist Generator** (`music_agent/playlist.py`):
  - `music-agent playlist` generates portable relative-path M3U8 playlists.
  - Automatically produces `All Tracks.m3u8`, category-specific playlists, and per-artist playlists (for artists with ≥2 tracks).
- **Library Health & Statistics** (`music_agent/library_stats.py`):
  - `music-agent stats` provides comprehensive library reporting in `table` or `json` format.
  - Tracks totals, format breakdown, category/artist breakdown, missing tags audit, and wishlist fulfillment.
- **One-Command Pipeline** (`music-agent full-sync`):
  - Unified pipeline executing organize → inventory → playlists → phone sync.
  - Supports `--dry-run`, `--execute`, `--enrich`, and modular `--skip-*` options.
- **Loudness & ReplayGain Analysis** (`music_agent/loudness.py`):
  - `music-agent analyze` computes EBU R128 loudness (Integrated LUFS, True Peak, LRA) via FFmpeg's `loudnorm` filter.
  - Optional `--write-tags` writes `REPLAYGAIN_TRACK_GAIN` and `REPLAYGAIN_TRACK_PEAK` tags using Mutagen (never re-encodes audio).
- **Acoustic & SHA-256 Duplicate Detection** (`music_agent/fingerprint.py`):
  - `music-agent dupes` scans library for duplicates using byte-level SHA-256 and optional AcoustID/Chromaprint fingerprinting via `fpcalc`.
  - Strictly advisory — reports matches without modifying or deleting files.
- **Advisory Fuzzy Artist Matching** (`music_agent/matcher.py`):
  - `fuzzy_suggest()` utilizes RapidFuzz to suggest canonical artist names for misspellings and typos.
  - Purely advisory to prevent accidental misrouting — exact matching remains authoritative.
- **Expanded Test Suite**:
  - Added 63 new tests across 6 new test modules (`test_enricher.py`, `test_artwork.py`, `test_playlist.py`, `test_library_stats.py`, `test_loudness.py`, `test_fingerprint.py`, `test_fuzzy_matcher.py`).
  - Total test count increased from 112 to 175 tests (100% pass rate).

### Security & Safety
- Maintained all V3.1 security guarantees: SSRF protection, private IP blocking, domain allowlisting, 250MB download cap, staging containment, and Zip Slip prevention.
- Maintained strict non-destructive policy: copy-only file operations, no automatic file deletion, no DRM circumvention, and no stream ripping.
- Baseline `v3.1.0` release tag preserved untouched.

---

## [3.1.0] - 2026-08-30

### Added
- Legitimate acquisition discovery engine with SSRF protections.
- Android ADB phone sync module (`music-agent sync-phone`).
- Folder watcher and ZIP archive ingestion pipeline.
- Curated catalog rules for 44 international, Telugu, and Hindi artists.
