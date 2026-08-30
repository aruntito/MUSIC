# Local Music Library Agent for macOS

A safe, privacy-preserving, local music library organizer and acquisition inventory agent designed for macOS. It curates, matches, sanitizes, and organizes audio files (MP3, M4A, FLAC, WAV, OGG, ZIP) into a structured artist directory hierarchy.

---

## ⚡ Core Highlights & Safety Guardrails

- 🛡️ **Copy-Only Safety**: Never deletes or moves original files from `~/Music/Inbox/` or `~/Downloads/`.
- 🎯 **Conservative Matching**: Exact and alias matches only. Never guesses on low confidence. Unrecognized tracks route safely to `~/Music/Review/`.
- 📋 **Wishlist & Inventory Tracking**: Compares your curated tracklist against local library storage to generate `missing.csv` and `inventory_report.md`.
- 📦 **Safe ZIP Ingestion & Zip Slip Protection**: Safely extracts audio from ZIP archives into temporary staging, ignoring non-audio files and blocking path traversal attacks.
- 👁️ **Folder Watcher**: Live foreground watcher with `--dry-run` and live modes for `~/Music/Inbox/` and `~/Downloads/`.
- 🔁 **100% Idempotent**: SHA-256 file hashing guarantees re-running never creates duplicate files.
- 🔒 **Completely Local & Offline**: No DRM bypass, no stream ripping, and no unauthorized scraping.

---

## 📂 Target Directory Structure

```text
~/Downloads/Songs/
  ├── International/
  │   ├── Billie Eilish/
  │   │   └── Billie Eilish - Ocean Eyes.mp3
  │   ├── XXXTentacion/
  │   │   └── XXXTentacion - Moonlight.mp3
  │   └── Wiz Khalifa/
  │       └── Wiz Khalifa - See You Again.m4a
  └── Indian/
      ├── Telugu/
      │   └── Sid Sriram - Samajavaragamana.mp3
      └── Hindi/
          └── Arijit Singh - Kesariya.mp3

~/Music/Review/
  └── UnmatchedArtist - UnrecognizedSong.mp3
```

---

## 🚀 Installation & Setup

```bash
cd /Users/arun/WORK/projects/MUSIC

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🛠️ Usage Guide

### 1. Check Configuration & Approved 44 Artists
```bash
python3 music_agent_cli.py check-config
```

### 2. Track Library Inventory & Missing Songs
Scan your local library against `config/wishlist.json` to generate `reports/missing.csv`:
```bash
python3 music_agent_cli.py inventory
```

### 3. Dry-Run Import Preview
Preview how files in `~/Music/Inbox/` will be categorized and renamed without modifying anything:
```bash
python3 music_agent_cli.py run --dry-run
```

### 4. Execute Safe Copy Import
Copy matched files to `~/Downloads/Songs/` and unmatched files to `~/Music/Review/`:
```bash
python3 music_agent_cli.py run --execute
```

### 5. Watch Folders for Incoming Downloads / ZIP Archives
Monitor `~/Music/Inbox` and `~/Downloads` in real-time (with safe ZIP unpacking into staging):
```bash
# Preview incoming files
python3 music_agent_cli.py watch --dry-run

# Live watcher (Copy-Only)
python3 music_agent_cli.py watch
```

### 6. Inspect Single Audio File Metadata
```bash
python3 music_agent_cli.py inspect "/path/to/song.mp3"
```

---

## 🧪 Running Automated Tests

```bash
.venv/bin/pytest -v
```

All 76 tests cover:
- 44/44 Curated artist routing
- Wishlist schema validation & duplicate detection
- Inventory comparison and `missing.csv` generation
- Safe ZIP extraction and Zip Slip security protection
- Watcher file detection and dry-run safety
- Idempotency, SHA-256 deduplication, and filename sanitization
