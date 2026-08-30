"""
Smart M3U8 Playlist Generator.

Scans ~/Downloads/Songs/ and generates relative-path M3U8 playlists:
  - All Tracks.m3u8        — full library
  - International.m3u8     — per category
  - Indian - Telugu.m3u8
  - Indian - Hindi.m3u8
  - <Artist>.m3u8          — per artist with ≥ MIN_TRACKS_FOR_ARTIST_PLAYLIST tracks

All paths in the generated M3U8 files are relative (portable to Android after sync).
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

SUPPORTED_AUDIO_EXTS: Set[str] = {".mp3", ".m4a", ".flac", ".wav", ".ogg"}
MIN_TRACKS_FOR_ARTIST_PLAYLIST = 2  # Generate a per-artist playlist if artist has ≥ this many tracks
M3U8_HEADER = "#EXTM3U\n"


@dataclass
class PlaylistEntry:
    relative_path: str       # Relative to the library root (or playlist dir)
    artist: Optional[str]
    title: Optional[str]
    duration_seconds: int = -1   # -1 = unknown


@dataclass
class GeneratedPlaylist:
    name: str
    path: Path
    entry_count: int


@dataclass
class PlaylistReport:
    library_root: Path
    playlist_dir: Path
    generated: List[GeneratedPlaylist] = field(default_factory=list)
    total_tracks_scanned: int = 0
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


def _read_duration(file_path: Path) -> int:
    """Attempt to read audio duration in seconds using mutagen. Returns -1 on failure."""
    try:
        import mutagen  # noqa: PLC0415
        audio = mutagen.File(str(file_path))
        if audio and audio.info:
            return int(audio.info.length)
    except Exception:
        pass
    return -1


def _extinf_line(entry: PlaylistEntry) -> str:
    """Format the #EXTINF line for an M3U8 entry."""
    display = entry.title or Path(entry.relative_path).stem
    if entry.artist:
        display = f"{entry.artist} - {display}"
    return f"#EXTINF:{entry.duration_seconds},{display}"


def _write_m3u8(playlist_path: Path, entries: List[PlaylistEntry]) -> GeneratedPlaylist:
    """Write an M3U8 file with relative paths. Creates parent dirs as needed."""
    playlist_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [M3U8_HEADER]
    for entry in entries:
        lines.append(_extinf_line(entry))
        lines.append(entry.relative_path)
        lines.append("")
    playlist_path.write_text("\n".join(lines), encoding="utf-8")
    return GeneratedPlaylist(name=playlist_path.stem, path=playlist_path, entry_count=len(entries))


def generate_playlists(
    library_root: Optional[Path] = None,
    playlist_dir: Optional[Path] = None,
) -> PlaylistReport:
    """
    Scan the organized library and generate M3U8 playlists.

    Args:
        library_root: Root of organized library. Defaults to ~/Downloads/Songs/.
        playlist_dir: Where to write .m3u8 files. Defaults to ./playlists/.

    Returns:
        PlaylistReport with list of generated playlists.
    """
    if library_root is None:
        library_root = Path.home() / "Downloads" / "Songs"
    if playlist_dir is None:
        playlist_dir = Path("playlists")

    library_root = Path(library_root).resolve()
    playlist_dir = Path(playlist_dir).resolve()

    report = PlaylistReport(library_root=library_root, playlist_dir=playlist_dir)

    if not library_root.exists():
        return report

    # Collect all audio files and build entries
    # Expected hierarchy: library_root / Category / Artist / ArtistName - Title.ext
    all_entries: List[PlaylistEntry] = []
    category_entries: Dict[str, List[PlaylistEntry]] = {}
    artist_entries: Dict[str, List[PlaylistEntry]] = {}

    for audio_file in sorted(library_root.rglob("*")):
        if not audio_file.is_file():
            continue
        if audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTS:
            continue
        if audio_file.name.startswith("."):
            continue

        # Derive relative path from library_root for M3U8 (portable)
        try:
            rel_path = audio_file.relative_to(library_root)
        except ValueError:
            continue

        # Parse category and artist from path parts
        # Expected: Category / Artist / File  (3+ parts)
        parts = rel_path.parts
        category = parts[0] if len(parts) >= 1 else "Unknown"
        artist = parts[1] if len(parts) >= 2 else None

        # Derive title from filename stem
        stem = audio_file.stem
        title = stem
        if artist and stem.startswith(artist + " - "):
            title = stem[len(artist) + 3:]
        elif " - " in stem:
            title = stem.split(" - ", 1)[1]

        duration = _read_duration(audio_file)

        # Use relative path from library_root (caller syncs playlists alongside library)
        # Use forward slashes for Android compatibility
        rel_str = str(rel_path).replace("\\", "/")

        entry = PlaylistEntry(
            relative_path=f"../Songs/{rel_str}",   # relative from playlists/ dir
            artist=artist,
            title=title,
            duration_seconds=duration,
        )

        all_entries.append(entry)
        category_entries.setdefault(category, []).append(entry)
        if artist:
            artist_entries.setdefault(artist, []).append(entry)

    report.total_tracks_scanned = len(all_entries)

    if not all_entries:
        return report

    # 1. Full library playlist
    report.generated.append(
        _write_m3u8(playlist_dir / "All Tracks.m3u8", all_entries)
    )

    # 2. Per-category playlists
    for category, entries in category_entries.items():
        # Normalise category name for filename
        safe_name = category.replace("/", " - ").strip()
        report.generated.append(
            _write_m3u8(playlist_dir / f"{safe_name}.m3u8", entries)
        )

    # 3. Per-artist playlists (≥ MIN_TRACKS threshold)
    artist_dir = playlist_dir / "Artists"
    for artist, entries in artist_entries.items():
        if len(entries) >= MIN_TRACKS_FOR_ARTIST_PLAYLIST:
            safe_artist = artist.replace("/", "-").strip()
            report.generated.append(
                _write_m3u8(artist_dir / f"{safe_artist}.m3u8", entries)
            )

    return report
