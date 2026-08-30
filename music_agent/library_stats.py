"""
Library Statistics and Health Report.

Scans ~/Downloads/Songs/ and produces:
  - Track count, total size
  - Breakdown by category, artist, and format
  - Tag health (tracks with missing artist/title/album/year)
  - Wishlist coverage (tracks present vs. total wanted)
  - Review queue count (unmatched files in ~/Music/Review/)
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

SUPPORTED_AUDIO_EXTS: Set[str] = {".mp3", ".m4a", ".flac", ".wav", ".ogg"}


@dataclass
class ArtistStats:
    canonical_name: str
    track_count: int = 0
    total_bytes: int = 0
    formats: Dict[str, int] = field(default_factory=dict)


@dataclass
class TagHealthItem:
    file_path: Path
    missing_fields: List[str]  # e.g. ["album", "year"]


@dataclass
class LibraryStats:
    library_root: Path
    review_dir: Path
    scanned_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    # Totals
    total_tracks: int = 0
    total_bytes: int = 0

    # Breakdowns
    by_category: Dict[str, int] = field(default_factory=dict)
    by_format: Dict[str, int] = field(default_factory=dict)
    by_artist: Dict[str, ArtistStats] = field(default_factory=dict)

    # Tag health
    tracks_missing_tags: List[TagHealthItem] = field(default_factory=list)

    # Wishlist coverage
    wishlist_total: int = 0
    wishlist_present: int = 0

    # Review queue
    review_count: int = 0
    review_bytes: int = 0


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def scan_library(
    library_root: Optional[Path] = None,
    review_dir: Optional[Path] = None,
    wishlist_path: Optional[Path] = None,
) -> LibraryStats:
    """
    Scan the organized library and return a LibraryStats snapshot.

    Args:
        library_root: Organized songs root. Defaults to ~/Downloads/Songs/.
        review_dir: Review directory. Defaults to ~/Music/Review/.
        wishlist_path: Path to config/wishlist.json. Auto-detected from project root.

    Returns:
        LibraryStats dataclass with all metrics populated.
    """
    if library_root is None:
        library_root = Path.home() / "Downloads" / "Songs"
    if review_dir is None:
        review_dir = Path.home() / "Music" / "Review"

    library_root = Path(library_root).resolve()
    review_dir = Path(review_dir).resolve()

    stats = LibraryStats(library_root=library_root, review_dir=review_dir)

    # ---- Scan main library ----
    if library_root.exists():
        for audio_file in sorted(library_root.rglob("*")):
            if not audio_file.is_file():
                continue
            ext = audio_file.suffix.lower()
            if ext not in SUPPORTED_AUDIO_EXTS:
                continue
            if audio_file.name.startswith("."):
                continue

            size = audio_file.stat().st_size
            stats.total_tracks += 1
            stats.total_bytes += size

            # Format breakdown
            fmt = ext.lstrip(".")
            stats.by_format[fmt] = stats.by_format.get(fmt, 0) + 1

            # Category + artist from path hierarchy
            try:
                rel = audio_file.relative_to(library_root)
            except ValueError:
                continue

            parts = rel.parts
            category = parts[0] if len(parts) >= 1 else "Unknown"
            artist = parts[1] if len(parts) >= 2 else None

            stats.by_category[category] = stats.by_category.get(category, 0) + 1

            if artist:
                if artist not in stats.by_artist:
                    stats.by_artist[artist] = ArtistStats(canonical_name=artist)
                a = stats.by_artist[artist]
                a.track_count += 1
                a.total_bytes += size
                a.formats[fmt] = a.formats.get(fmt, 0) + 1

            # Tag health check using mutagen
            missing = _check_missing_tags(audio_file)
            if missing:
                stats.tracks_missing_tags.append(TagHealthItem(audio_file, missing))

    # ---- Scan review queue ----
    if review_dir.exists():
        for f in review_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in SUPPORTED_AUDIO_EXTS:
                stats.review_count += 1
                stats.review_bytes += f.stat().st_size

    # ---- Wishlist coverage ----
    if wishlist_path is None:
        # Auto-detect: look for config/wishlist.json relative to project
        candidate = Path(__file__).resolve().parent.parent / "config" / "wishlist.json"
        if candidate.exists():
            wishlist_path = candidate

    if wishlist_path and Path(wishlist_path).exists():
        import json  # noqa: PLC0415
        try:
            with open(wishlist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            tracks = data.get("tracks", [])
            stats.wishlist_total = len(tracks)

            # A wishlist track is "present" if any audio file exists under
            # the artist's expected folder in the library
            for track in tracks:
                artist = track.get("artist", "")
                title = track.get("title", "")
                if _track_present_in_library(library_root, artist, title):
                    stats.wishlist_present += 1
        except Exception:
            pass

    return stats


def _check_missing_tags(audio_file: Path) -> List[str]:
    """Return list of missing essential tag field names for the file."""
    try:
        import mutagen  # noqa: PLC0415
        audio = mutagen.File(str(audio_file))
        if audio is None or audio.tags is None:
            return ["artist", "title", "album", "year"]

        from music_agent.metadata import _first_tag_value  # noqa: PLC0415
        tags = audio.tags
        missing = []

        if not _first_tag_value(tags, ["artist", "ARTIST", "\xa9ART", "TPE1"]):
            missing.append("artist")
        if not _first_tag_value(tags, ["title", "TITLE", "\xa9nam", "TIT2"]):
            missing.append("title")
        if not _first_tag_value(tags, ["album", "ALBUM", "\xa9alb", "TALB"]):
            missing.append("album")
        if not _first_tag_value(tags, ["date", "DATE", "\xa9day", "TDRC", "TYER"]):
            missing.append("year")
        return missing
    except Exception:
        return []


def _track_present_in_library(library_root: Path, artist: str, title: str) -> bool:
    """
    Check whether an audio file for the given artist/title exists in the library.
    Uses a case-insensitive filename prefix match.
    """
    artist_lower = artist.lower()
    title_lower = title.lower()

    for audio_file in library_root.rglob("*"):
        if not audio_file.is_file():
            continue
        if audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTS:
            continue
        stem_lower = audio_file.stem.lower()
        if artist_lower in stem_lower and title_lower in stem_lower:
            return True
    return False


def format_stats_table(stats: LibraryStats) -> str:
    """Format stats as a plain-text summary (fallback for --no-color mode)."""
    lines = [
        "=" * 60,
        "  MUSIC LIBRARY STATISTICS",
        "=" * 60,
        f"  Library Root:      {stats.library_root}",
        f"  Scanned At:        {stats.scanned_at}",
        "",
        f"  Total Tracks:      {stats.total_tracks}",
        f"  Total Size:        {_human_size(stats.total_bytes)}",
        "",
        "  --- By Format ---",
    ]
    for fmt, count in sorted(stats.by_format.items(), key=lambda x: -x[1]):
        lines.append(f"    .{fmt:<8}  {count} tracks")

    lines.append("")
    lines.append("  --- By Category ---")
    for cat, count in sorted(stats.by_category.items()):
        lines.append(f"    {cat:<28} {count} tracks")

    lines.append("")
    lines.append(f"  --- Tag Health ---")
    lines.append(f"    Tracks with missing tags: {len(stats.tracks_missing_tags)}")
    for item in stats.tracks_missing_tags[:10]:   # show first 10
        lines.append(f"    ⚠  {item.file_path.name}  missing: {', '.join(item.missing_fields)}")
    if len(stats.tracks_missing_tags) > 10:
        lines.append(f"    ... and {len(stats.tracks_missing_tags) - 10} more")

    lines.append("")
    lines.append("  --- Wishlist Coverage ---")
    if stats.wishlist_total > 0:
        pct = 100.0 * stats.wishlist_present / stats.wishlist_total
        lines.append(f"    {stats.wishlist_present} / {stats.wishlist_total} tracks ({pct:.0f}%)")
    else:
        lines.append("    No wishlist found")

    lines.append("")
    lines.append("  --- Review Queue ---")
    lines.append(f"    Unmatched files: {stats.review_count}  ({_human_size(stats.review_bytes)})")
    lines.append("=" * 60)
    return "\n".join(lines)
