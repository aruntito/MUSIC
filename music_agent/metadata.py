"""
Audio metadata extraction using Mutagen with safe filename fallback heuristics.
"""

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Optional
import mutagen

# Common junk suffixes and tags in download filenames
CLEANUP_REGEX = re.compile(
    r'(\s*\[(Official Video|Official Audio|Lyrics|Lyric Video|Audio|Visualizer|HQ|HD|320kbps|Remastered|Explicit)\]|\s*\((Official Video|Official Audio|Lyrics|Lyric Video|Audio|Visualizer|HQ|HD|320kbps|Remastered|Explicit)\))',
    re.IGNORECASE
)
TRACK_PREFIX_REGEX = re.compile(r'^\s*(\d{1,3}[\.\-_\s]+)')


@dataclass
class AudioMetadata:
    file_path: Path
    artist: Optional[str] = None
    album_artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    year: Optional[str] = None
    genre: Optional[str] = None
    track_number: Optional[str] = None
    has_embedded_metadata: bool = False
    metadata_source: str = "none"  # "tags", "filename", "partial"


def clean_title_or_artist(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    cleaned = CLEANUP_REGEX.sub("", text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned if cleaned else None


def extract_metadata_from_filename(file_path: Path) -> tuple[Optional[str], Optional[str]]:
    """
    Fallback parser extracting (artist, title) from filename stem.
    Examples:
      - 'Billie Eilish - Ocean Eyes.mp3' -> ('Billie Eilish', 'Ocean Eyes')
      - '01. Wiz Khalifa - See You Again [Official Audio].m4a' -> ('Wiz Khalifa', 'See You Again')
      - 'Kesariya.mp3' -> (None, 'Kesariya')
    """
    stem = file_path.stem
    stem = CLEANUP_REGEX.sub("", stem).strip()
    # Strip leading track numbers like "01. " or "01 - "
    stem_without_track = TRACK_PREFIX_REGEX.sub("", stem).strip()

    # Look for delimiters: " - ", " _ "
    if " - " in stem_without_track:
        parts = stem_without_track.split(" - ", 1)
        artist = clean_title_or_artist(parts[0])
        title = clean_title_or_artist(parts[1])
        return artist, title
    elif " – " in stem_without_track:  # en-dash
        parts = stem_without_track.split(" – ", 1)
        artist = clean_title_or_artist(parts[0])
        title = clean_title_or_artist(parts[1])
        return artist, title
    elif "_" in stem_without_track and not " " in stem_without_track:
        parts = stem_without_track.split("_", 1)
        artist = clean_title_or_artist(parts[0])
        title = clean_title_or_artist(parts[1])
        return artist, title

    # Just title
    return None, clean_title_or_artist(stem_without_track or stem)


def _first_tag_value(tags, keys: list[str]) -> Optional[str]:
    """Helper to retrieve the first present key value from a mutagen tag dict safely."""
    if tags is None:
        return None
    for key in keys:
        try:
            val = None
            if hasattr(tags, "get"):
                val = tags.get(key)
            elif hasattr(tags, "__getitem__"):
                val = tags[key]
            
            if val is not None:
                if isinstance(val, (list, tuple)) and len(val) > 0:
                    val = val[0]
                val_str = str(val).strip()
                if val_str:
                    return val_str
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
    return None


def read_audio_metadata(file_path: Path) -> AudioMetadata:
    """
    Read embedded metadata using Mutagen for MP3, M4A, FLAC, OGG, WAV.
    Falls back gracefully to filename parsing if metadata is missing.
    """
    path = Path(file_path).resolve()
    artist: Optional[str] = None
    album_artist: Optional[str] = None
    title: Optional[str] = None
    album: Optional[str] = None
    year: Optional[str] = None
    genre: Optional[str] = None
    track_number: Optional[str] = None
    has_tags = False

    try:
        audio = mutagen.File(str(path))
        if audio is not None and audio.tags:
            tags = audio.tags

            # Artist
            artist = _first_tag_value(tags, ["artist", "ARTIST", "\xa9ART", "TPE1", "Author", "IART"])
            # Album Artist
            album_artist = _first_tag_value(tags, ["albumartist", "ALBUMARTIST", "aART", "TPE2", "ALBUM ARTIST"])
            # Title
            title = _first_tag_value(tags, ["title", "TITLE", "\xa9nam", "TIT2", "INAM"])
            # Album
            album = _first_tag_value(tags, ["album", "ALBUM", "\xa9alb", "TALB", "IPRD"])
            # Year
            year = _first_tag_value(tags, ["date", "DATE", "\xa9day", "TDRC", "TYER", "year", "YEAR"])
            if year:
                # Normalise to 4-digit year if possible (e.g. "2020-01-01" → "2020")
                year = str(year).strip()[:4] if str(year).strip() else None
            # Genre
            genre = _first_tag_value(tags, ["genre", "GENRE", "\xa9gen", "TCON"])
            # Track number
            trkn = (
                _first_tag_value(tags, ["tracknumber", "TRACKNUMBER", "TRCK", "ITRK"]) or
                getattr(tags, "get", lambda k: None)("trkn")
            )
            if trkn:
                if isinstance(trkn, (list, tuple)) and len(trkn) > 0:
                    trkn = trkn[0]
                if isinstance(trkn, tuple) and len(trkn) > 0:
                    track_number = str(trkn[0])
                else:
                    track_number = str(trkn).split("/")[0].strip()

            artist = clean_title_or_artist(artist)
            album_artist = clean_title_or_artist(album_artist)
            title = clean_title_or_artist(title)
            album = clean_title_or_artist(album)
            genre = clean_title_or_artist(genre)

            if artist or title:
                has_tags = True

    except Exception:
        # If mutagen fails or file is corrupt/unsupported, keep has_tags = False
        pass

    # Apply fallback if artist or title are missing
    fn_artist, fn_title = extract_metadata_from_filename(path)

    if not artist and fn_artist:
        artist = fn_artist
    if not title:
        title = fn_title or path.stem

    if has_tags and (not artist or not title):
        source = "partial"
    elif has_tags:
        source = "tags"
    else:
        source = "filename"

    return AudioMetadata(
        file_path=path,
        artist=artist,
        album_artist=album_artist,
        title=title,
        album=album,
        year=year,
        genre=genre,
        track_number=track_number,
        has_embedded_metadata=has_tags,
        metadata_source=source,
    )
