# Music Library Agent

**Safe, local music library organizer for macOS** — automatically organizes audio files, enriches metadata, detects duplicates, analyzes loudness, generates smart playlists, tracks your wishlist against your collection, and syncs music to your Android phone via ADB.

> A privacy-preserving, copy-only Python CLI tool for managing your personal music collection on macOS. No stream ripping. No DRM bypass. No cloud dependency.

---

## Features

| Capability | Details |
|---|---|
| 🗂️ **Music File Organizer** | Copies and renames audio files into `Category/Artist/Artist - Title.ext` hierarchy |
| 🔁 **Duplicate Detection** | Byte-level SHA-256 and optional AcoustID/Chromaprint acoustic fingerprinting |
| 📋 **Wishlist & Inventory Tracking** | JSON wishlist diffed against local library to produce `missing.csv` |
| 🎵 **Metadata Inspection & Enrichment** | Reads tags via `mutagen`; optional online enrichment via MusicBrainz (`--enrich`) |
| 🖼️ **Album Artwork** | Cover Art Archive integration: embed artwork in tags and/or save `folder.jpg` |
| 🔊 **ReplayGain & Loudness Analysis** | EBU R128 loudness measurement and ReplayGain 2.0 tagging via FFmpeg |
| 📃 **Smart M3U8 Playlists** | Generates portable relative-path playlists: All Tracks, Categories, and Artists |
| 📊 **Library Health & Statistics** | Detailed reporting on formats, sizes, missing tags, wishlist coverage |
| 🚀 **One-Command Pipeline** | `full-sync` orchestrates organize → inventory → playlists → phone sync |
| 📦 **Safe ZIP Ingestion** | Extracts audio from ZIP archives; blocks Zip Slip path traversal attacks |
| 👁️ **Folder Watcher** | Real-time watch on `~/Music/Inbox/` and `~/Downloads/` with dry-run preview |
| 🔍 **Acquisition Discovery** | Searches legitimate open sources; classifies commercial tracks as purchase-required |
| 📱 **Android Phone Sync** | Copies organized library to Android via ADB (`adb push`) or mounted storage |
| 🛡️ **Security-First Design** | SSRF protection, DNS/IP validation, redirect blocking, staging containment, size limits |
| 🧪 **Comprehensive Tests** | 175 unit tests across 19 test suites with 100% pass rate |

---

## Why Music Library Agent?

Most music management tools either require a cloud subscription, manipulate your existing files destructively, or make it too easy to accidentally rip or download music from unauthorized sources.

Music Library Agent is built around three constraints:

1. **Copy-only** — your source files are never moved, renamed, or deleted.
2. **Locally private** — offline by default. No data leaves your Mac unless you explicitly run `--enrich`.
3. **Copyright-respecting** — the acquisition layer explicitly classifies commercial tracks as `PURCHASE_REQUIRED` and will not attempt stream ripping, DRM circumvention, or unauthorized scraping.

---

## Supported Formats

`MP3` · `M4A` · `FLAC` · `WAV` · `OGG` · `ZIP` (auto-extracted)

---

## Installation

### Requirements

- macOS (tested on macOS Sonoma / Ventura / Sequoia)
- Python 3.10 or later
- `ffmpeg` (for ReplayGain loudness analysis) — optional
- `adb` from Android Platform Tools (for Android phone sync) — optional
- `fpcalc` from Chromaprint (for acoustic duplicate detection) — optional

### Setup

```bash
git clone https://github.com/aruntito/MUSIC.git
cd MUSIC

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Optional External Tools

```bash
# For Android sync
brew install android-platform-tools

# For loudness/ReplayGain analysis
brew install ffmpeg

# For acoustic fingerprinting
brew install chromaprint
```

---

## Quick Start

```bash
# 1. Preview how files in ~/Music/Inbox/ will be organized
python music_agent_cli.py run --dry-run

# 2. Execute the import (copy-only — source files are never modified)
python music_agent_cli.py run --execute

# 3. Check library statistics and tag health
python music_agent_cli.py stats

# 4. Generate M3U8 playlists
python music_agent_cli.py playlist

# 5. One-command full sync to Android phone
python music_agent_cli.py full-sync --dry-run
python music_agent_cli.py full-sync --execute
```

---

## CLI Reference

All commands default to safe preview/dry-run modes where applicable.

### 1. `run` — Ingest & Organize

```bash
# Dry-run preview
python music_agent_cli.py run --dry-run

# Execute live copy-import
python music_agent_cli.py run --execute --source ~/Music/Inbox --dest ~/Downloads/Songs
```

### 2. `stats` — Library Statistics & Health

```bash
# View library table report
python music_agent_cli.py stats

# Export JSON metrics
python music_agent_cli.py stats --format json
```

### 3. `playlist` — Generate M3U8 Playlists

```bash
# Generate relative-path playlists in ./playlists/
python music_agent_cli.py playlist
```

### 4. `full-sync` — Unified Workflow

```bash
# Preview the complete workflow
python music_agent_cli.py full-sync --dry-run

# Execute organize + inventory + playlists + Android sync
python music_agent_cli.py full-sync --execute

# Execute with MusicBrainz enrichment
python music_agent_cli.py full-sync --execute --enrich
```

### 5. `analyze` — ReplayGain Loudness Analysis

```bash
# Analyze library loudness
python music_agent_cli.py analyze --path ~/Downloads/Songs

# Analyze and write ReplayGain tags (without re-encoding audio)
python music_agent_cli.py analyze --path ~/Downloads/Songs --write-tags
```

### 6. `dupes` — Duplicate Detection

```bash
# Scan for SHA-256 and acoustic duplicates
python music_agent_cli.py dupes --path ~/Downloads/Songs
```

### 7. `sync-phone` — Android Sync

```bash
# Preview transfer to Android device via ADB
python music_agent_cli.py sync-phone --dry-run

# Execute sync
python music_agent_cli.py sync-phone --execute
```

### 8. `inspect` — Single File Inspector

```bash
# Inspect embedded tags and match result
python music_agent_cli.py inspect "song.mp3"

# Inspect and enrich with MusicBrainz lookup
python music_agent_cli.py inspect "song.mp3" --enrich
```

### 9. `inventory` — Wishlist Diffing

```bash
python music_agent_cli.py inventory
```

### 10. `watch` — Real-Time Folder Monitoring

```bash
python music_agent_cli.py watch --watch-dir ~/Downloads --watch-dir ~/Music/Inbox
```

---

## Security & Safety Model

### SSRF & Network Protection

The acquisition layer enforces strict SSRF (Server-Side Request Forgery) protection:

- **DNS resolution validation** — all download URLs are resolved and rejected if the resolved IP falls within RFC1918 private ranges (`10.x`, `172.16–31.x`, `192.168.x`), loopback (`127.x`), link-local, or any other non-routable block.
- **Redirect validation** — HTTP redirects are followed up to a limited depth; each redirect destination IP is re-validated.
- **Domain allowlist** — only explicitly approved source domains can be used for acquisition.
- **Download size limit** — files exceeding 250 MB are rejected before download completes.
- **Staging containment** — all downloads go to a temporary staging directory; they are only promoted after verification.

### File Safety

- **Zip Slip protection** — ZIP extraction validates that no archive member escapes the staging sandbox.
- **SHA-256 deduplication** — content hash identity prevents duplicate file copies.
- **Filename sanitization** — names are sanitized for both macOS and Android filesystem compatibility.
- **Copy-only ingestion** — source files are never moved, renamed, or deleted.

---

## Architecture

```
music_agent/
├── cli.py            # argparse CLI — all subcommands & dispatch
├── config.py         # Configuration loader (library_rules.json)
├── organizer.py      # Core file ingestion & copy pipeline
├── matcher.py        # Curated exact matching & RapidFuzz advisory suggestions
├── sanitizer.py      # Filename sanitization for macOS / Android
├── metadata.py       # Audio metadata reading (mutagen)
├── enricher.py       # MusicBrainz metadata enrichment & local caching
├── artwork.py        # Cover Art Archive fetcher & tag embedding
├── playlist.py       # Smart relative-path M3U8 playlist generator
├── library_stats.py  # Library metrics, health audit & stats reporting
├── loudness.py       # FFmpeg EBU R128 loudness & ReplayGain tagging
├── fingerprint.py    # SHA-256 and AcoustID duplicate detection
├── deduplicator.py   # SHA-256 library content indexing
├── inventory.py      # Wishlist JSON parser + library diff → missing.csv
├── reporter.py       # Markdown & CSV report generation
├── watcher.py        # Folder watcher (real-time inbox monitoring)
├── acquisition.py    # Legitimate acquisition discovery & staging engine
├── phone_sync.py     # Android phone sync (ADB + Directory backends)
└── connectors/
    ├── base.py            # BaseConnector ABC, URL validation, SSRF guard
    ├── official_stores.py # Official store purchase link generation
    ├── public_archive.py  # Public domain / open-license source connector
    └── manual.py          # Manual local file connector
```

---

## Testing

```bash
# Run the full test suite
.venv/bin/pytest -v
```

```
============================= 175 passed in 2.18s ==============================
```

Test coverage includes:
- 44/44 curated artist routing (International, Telugu, Hindi categories)
- Metadata extraction and enrichment (MusicBrainz mock API + local cache)
- Album artwork embedding and folder.jpg management
- Smart M3U8 playlist generation and relative path portability
- Library statistics scanning, tag health, and wishlist metrics
- EBU R128 loudness analysis and ReplayGain tag writing
- AcoustID acoustic fingerprinting and duplicate detection
- Advisory fuzzy artist matching with RapidFuzz
- Safe ZIP extraction and Zip Slip path traversal blocking
- Folder watcher detection and dry-run safety
- SHA-256 deduplication and idempotency
- Filename sanitization (macOS + Android compatible)
- Acquisition pipeline and SSRF protections
- Android phone sync — ADB backend, Directory backend, and deduplication
- Complete CLI subcommand parsing and execution

---

## Contributing

Contributions are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on code style, test requirements, and contribution boundaries.

---

## Security Policy

For security concerns and vulnerability reporting, please refer to [SECURITY.md](SECURITY.md).

---

## License

Private repository. All rights reserved unless otherwise stated.
