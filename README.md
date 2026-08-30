# Music Library Agent

**Safe, local music library organizer for macOS** — automatically organizes audio files, detects duplicates, tracks your wishlist against your collection, and syncs music to your Android phone via ADB.

> A privacy-preserving, copy-only Python CLI tool for managing your personal music collection on macOS. No stream ripping. No DRM bypass. No cloud dependency.

---

## Features

| Capability | Details |
|---|---|
| 🗂️ **Music File Organizer** | Copies and renames audio files into `Category/Artist/Artist - Title.ext` hierarchy |
| 🔁 **Duplicate Detection** | SHA-256 hashing prevents duplicate files at the destination |
| 📋 **Wishlist & Inventory Tracking** | JSON wishlist diffed against local library to produce `missing.csv` |
| 🎵 **Metadata Inspection** | Reads ID3/M4A/FLAC tags via `mutagen` |
| 📦 **Safe ZIP Ingestion** | Extracts audio from ZIP archives; blocks Zip Slip path traversal attacks |
| 👁️ **Folder Watcher** | Real-time watch on `~/Music/Inbox/` and `~/Downloads/` with dry-run preview |
| 🔍 **Acquisition Discovery** | Searches legitimate, open-licensed sources; classifies commercial tracks as purchase-required |
| 📱 **Android Phone Sync** | Copies organized library to Android via ADB (`adb push`) or mounted USB storage |
| 🛡️ **Security-First Design** | SSRF protection, DNS/IP validation, redirect blocking, staging containment, size limits |
| 🧪 **Comprehensive Tests** | 112 unit tests across all modules |

---

## Why Music Library Agent?

Most music management tools either require a cloud subscription, manipulate your existing files destructively, or make it too easy to accidentally rip or download music from unauthorized sources.

Music Library Agent is built around three constraints:

1. **Copy-only** — your source files are never moved, renamed, or deleted.
2. **Locally private** — no data leaves your Mac. No accounts. No API keys required for basic operation.
3. **Copyright-respecting** — the acquisition layer explicitly classifies commercial tracks as `PURCHASE_REQUIRED` and will not attempt stream ripping, DRM circumvention, or unauthorized scraping.

It is designed for music collectors who own their files and want an automated, reproducible way to organize them.

---

## Supported Formats

`MP3` · `M4A` · `FLAC` · `WAV` · `OGG` · `ZIP` (auto-extracted)

---

## Installation

### Requirements

- macOS (tested on macOS Sonoma / Ventura)
- Python 3.10 or later
- `adb` from Android Platform Tools — *only required for Android sync*

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

### Install `adb` (for Android sync only)

```bash
brew install android-platform-tools
```

---

## Quick Start

```bash
# 1. Preview how files in ~/Music/Inbox/ will be organized
python music_agent_cli.py run --dry-run

# 2. Execute the import (copy-only — source files are never modified)
python music_agent_cli.py run --execute

# 3. Check your wishlist against your local library
python music_agent_cli.py inventory

# 4. Preview what would be sent to your Android phone
python music_agent_cli.py sync-phone --dry-run

# 5. Transfer music to Android via ADB
python music_agent_cli.py sync-phone --execute
```

---

## CLI Reference

All commands default to `--dry-run` where applicable. Destructive operations require explicit `--execute`.

### `run` — Organize music from Inbox

```bash
# Dry-run preview (no files are copied)
python music_agent_cli.py run --dry-run

# Live import: copies matched files to ~/Downloads/Songs/, unmatched to ~/Music/Review/
python music_agent_cli.py run --execute

# Custom source/destination
python music_agent_cli.py run --execute --source ~/Desktop/NewMusic --dest ~/Music/Organized
```

### `inventory` — Wishlist vs. local library diff

```bash
# Scan ~/Downloads/Songs/ and produce reports/missing.csv + reports/inventory_report.md
python music_agent_cli.py inventory
```

### `acquire` — Legitimate acquisition discovery

```bash
# Discover which wishlist tracks are freely/openly available vs. purchase-required
python music_agent_cli.py acquire --dry-run

# Attempt to stage openly licensed tracks (purchase-required tracks are never downloaded)
python music_agent_cli.py acquire --execute
```

### `sync-phone` — Android phone music sync

```bash
# Preview transfer via ADB to /sdcard/Music/ (dry-run by default)
python music_agent_cli.py sync-phone

# Preview transfer to mounted USB drive / SD card
python music_agent_cli.py sync-phone --backend directory --target-dir /Volumes/PhoneSD/Music

# Execute ADB transfer
python music_agent_cli.py sync-phone --execute

# Execute to mounted storage
python music_agent_cli.py sync-phone --execute --backend directory --target-dir /Volumes/PhoneSD/Music
```

`sync-phone` never deletes files from your phone. Files already present on the device are skipped.

### `watch` — Folder watcher for incoming files

```bash
# Dry-run: show what would happen when new files land in ~/Music/Inbox
python music_agent_cli.py watch --dry-run

# Live watcher (copy-only)
python music_agent_cli.py watch
```

### `inspect` — Read metadata from a single audio file

```bash
python music_agent_cli.py inspect "/path/to/song.mp3"
```

### `check-config` — Validate configuration and artist list

```bash
python music_agent_cli.py check-config
```

---

## Music Organization

Files placed in `~/Music/Inbox/` (or `~/Downloads/`) are matched against the configured curated artist list (44 artists across International, Indian/Telugu, and Indian/Hindi categories).

**Matched files** are copied to a structured destination:

```
~/Downloads/Songs/
├── International/
│   ├── Billie Eilish/
│   │   └── Billie Eilish - Ocean Eyes.mp3
│   ├── Arctic Monkeys/
│   │   └── Arctic Monkeys - Do I Wanna Know.mp3
│   └── Linkin Park/
│       └── Linkin Park - Numb.mp3
└── Indian/
    ├── Telugu/
    │   ├── Anirudh Ravichander/
    │   │   └── Anirudh Ravichander - Hukum.mp3
    │   └── Sid Sriram/
    │       └── Sid Sriram - Samajavaragamana.mp3
    └── Hindi/
        └── Arijit Singh/
            └── Arijit Singh - Kesariya.mp3
```

**Unmatched files** are routed safely to `~/Music/Review/` for manual inspection — they are never silently dropped.

---

## Android Phone Sync

Music Library Agent can synchronize your organized library to your Android phone via two transport backends:

### ADB Backend (USB debugging)

1. Enable **Developer Options → USB Debugging** on your phone.
2. Connect via USB and accept the "Allow USB debugging?" prompt.
3. Verify connection: `adb devices`
4. Run the sync: `python music_agent_cli.py sync-phone --execute`

Files are pushed to `/sdcard/Music/` by default, preserving the `Category/Artist/` folder structure.

### Directory Backend (Mounted storage / USB OTG)

```bash
python music_agent_cli.py sync-phone --execute \
  --backend directory \
  --target-dir /Volumes/PhoneSD/Music
```

Works with SD cards, USB-C OTG drives, or any mounted Android volume.

### Sync Safety Guarantees

- **Copy-only**: Zero delete/remove/prune operations exist in either backend.
- **Duplicate skipping**: Files already on the device (matched by relative path + size) are skipped as `ALREADY_EXISTS`.
- **Foreign file preservation**: Music already on your phone that is not in the library is untouched.
- **Post-transfer verification**: Destination file size is verified after each transfer.
- **Reports generated**: `reports/phone_sync_report.md` + `reports/phone_sync_manifest.csv`

---

## Acquisition Discovery

The `acquire` command searches openly licensed sources (e.g. public domain archives) for tracks on your `config/wishlist.json`. Commercial tracks are classified as `PURCHASE_REQUIRED`.

**What it does NOT do:**
- Stream rip from Spotify, YouTube Music, Apple Music, or any streaming service.
- Circumvent DRM or licensing restrictions.
- Download copyrighted music without a verifiable open license.

If a track cannot be obtained from an open, policy-approved source, it is reported as `PURCHASE_REQUIRED` and the acquisition step is skipped. The user is responsible for supplying purchased files into `~/Music/Inbox/`.

---

## Security

### SSRF & Network Protection

The acquisition layer enforces strict SSRF (Server-Side Request Forgery) protection:

- **DNS resolution validation** — all download URLs are resolved and rejected if the resolved IP falls within RFC1918 private ranges (`10.x`, `172.16–31.x`, `192.168.x`), loopback (`127.x`), link-local, or any other non-routable block.
- **Redirect validation** — HTTP redirects are followed up to a limited depth; each redirect destination IP is re-validated.
- **Domain allowlist** — only explicitly approved source domains can be used for acquisition.
- **Download size limit** — files exceeding 250 MB are rejected before download completes.
- **Staging containment** — all downloads go to a temporary staging directory; they are only promoted to the library after successful metadata validation and organizer processing.
- **Zero partial files** — failed or oversized downloads are discarded; partial files are never promoted.

### File Safety

- **Zip Slip protection** — ZIP extraction validates that no archive member escapes the staging sandbox via `../` path traversal.
- **SHA-256 deduplication** — file identity is established by content hash, not filename.
- **Filename sanitization** — names are sanitized for both macOS and Android filesystem compatibility before any file is written.
- **Copy-only ingestion** — source files are never moved or deleted.

---

## Architecture

```
music_agent/
├── cli.py            # argparse CLI — all subcommands
├── config.py         # Configuration loader (library_rules.json)
├── organizer.py      # Core file ingestion & copy pipeline
├── matcher.py        # Artist & title matching (curated list + aliases)
├── sanitizer.py      # Filename sanitization for macOS / Android
├── metadata.py       # Audio metadata reading (mutagen)
├── deduplicator.py   # SHA-256 content hashing
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

```
config/
├── library_rules.json    # Artist rules, category mapping, file naming format
└── wishlist.json         # Curated track wishlist (44 artists)

tests/                    # 112 unit tests
```

---

## Testing

```bash
# Run the full test suite
.venv/bin/pytest -v
```

```
112 passed in 0.38s
```

Test coverage includes:
- 44/44 curated artist routing (International, Telugu, Hindi categories)
- Wishlist schema validation and duplicate detection
- Inventory diff and `missing.csv` generation
- Safe ZIP extraction and Zip Slip path traversal blocking
- Folder watcher detection and dry-run safety
- SHA-256 deduplication and idempotency
- Filename sanitization (macOS + Android compatible)
- Acquisition pipeline (open-license vs. purchase-required classification)
- SSRF protection, DNS/IP private-range validation, redirect depth limiting
- Download size limit enforcement
- Android phone sync — ADB backend (mocked), Directory backend, deduplication, foreign file preservation
- CLI flag parsing and validation

---

## Limitations

- **No automatic music downloads for commercial tracks.** Tracks classified as `PURCHASE_REQUIRED` must be supplied manually.
- **Matching is conservative.** Only exact artist name matches and configured aliases are accepted. Unknown artists route to `~/Music/Review/`.
- **44 artists currently configured.** Adding more requires editing `config/library_rules.json`.
- **ADB sync requires Android USB debugging enabled** on the target device.
- **macOS only.** The file path assumptions and tested filesystem behavior target macOS.

---

## Roadmap

- [ ] Expand curated artist list beyond 44 entries
- [ ] Add artist alias bulk import
- [ ] Support configurable fuzzy match threshold option
- [ ] Support reading embedded cover art
- [ ] Add MusicBrainz metadata lookup for untagged files
- [ ] Support wireless ADB (ADB over TCP/IP) for Wi-Fi phone sync
- [ ] Add progress bar for large batch transfers

---

## FAQ

**How do I organize a music library on macOS?**
Place your audio files (MP3, M4A, FLAC, WAV, OGG, or ZIP) into `~/Music/Inbox/`, run `python music_agent_cli.py run --dry-run` to preview, then `python music_agent_cli.py run --execute` to copy them into the organized `~/Downloads/Songs/` hierarchy.

**How do I automatically organize music files?**
The `watch` command monitors your inbox folder in real time and processes new files as they arrive: `python music_agent_cli.py watch`.

**How do I detect duplicate music files?**
Music Library Agent uses SHA-256 file hashing. If a file with the same content already exists at the destination, the copy is skipped. Run `python music_agent_cli.py run --dry-run` to preview before committing.

**How do I sync music from Mac to Android?**
Connect your phone via USB with ADB debugging enabled, then run `python music_agent_cli.py sync-phone --execute`. The organized `~/Downloads/Songs/` library is mirrored to `/sdcard/Music/` on the device.

**How does ADB music transfer work?**
The `sync-phone` command uses `adb push` to transfer files. It first queries existing files on the device to skip duplicates, then copies new files and verifies the destination size after each transfer.

**How does Music Library Agent handle copyrighted music?**
Commercial tracks on your wishlist are classified as `PURCHASE_REQUIRED`. The agent reports them and provides purchase links, but does not attempt to download them. You supply purchased files manually into `~/Music/Inbox/`.

**Does it rip Spotify, YouTube, or Apple Music streams?**
No. Stream ripping and DRM circumvention are explicitly not implemented and will not be added. This is a hard design constraint, not a temporary limitation.

**Does it delete existing music files?**
No. Neither the organizer nor the phone sync module deletes files from source, destination, or device. The organizer copies files; `sync-phone` copies files. Existing files are preserved at every step.

**Can I add more artists to the curated list?**
Yes. Edit `config/library_rules.json` and add artist entries under the appropriate category. Run `python music_agent_cli.py check-config` to validate.

**What happens to unrecognized files?**
Files that do not match any configured artist are copied to `~/Music/Review/` for manual review. They are never silently dropped.

---

## Contributing

Contributions are welcome. Please:

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/your-feature`).
3. Write or update tests for any changed behavior.
4. Ensure `pytest` passes: `.venv/bin/pytest -v`
5. Open a pull request with a clear description of the change.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full contribution guidelines.

---

## Security Policy

For security vulnerabilities, please read [SECURITY.md](SECURITY.md) before opening an issue.

---

## License

Private repository. All rights reserved unless otherwise stated.
