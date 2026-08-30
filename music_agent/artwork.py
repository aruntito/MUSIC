"""
Album Artwork Module — embed artwork into audio files and/or save as folder.jpg.

Artwork is ONLY fetched when --enrich is explicitly enabled.
Never fetches artwork during normal offline operation.

Embedding modifies destination audio file tags only (no re-encoding).
Supported formats: MP3 (ID3 APIC), M4A (covr), FLAC (PICTURE).
"""

import hashlib
from pathlib import Path
from typing import Optional
import urllib.request


# Artwork mode constants
MODE_EMBED = "embed"
MODE_FOLDER_JPG = "folder_jpg"
MODE_BOTH = "both"
DEFAULT_MODE = MODE_BOTH


def download_artwork(url: str, cache_dir: Optional[Path] = None) -> Optional[bytes]:
    """
    Download artwork image bytes from a URL.
    Caches by URL hash under ~/.cache/music-agent/artwork/.
    Returns raw JPEG bytes or None on failure.
    """
    if not url:
        return None

    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "music-agent" / "artwork"
    cache_dir.mkdir(parents=True, exist_ok=True)

    url_hash = hashlib.sha256(url.encode()).hexdigest()[:16]
    cache_file = cache_dir / f"{url_hash}.jpg"

    if cache_file.exists():
        try:
            return cache_file.read_bytes()
        except IOError:
            pass

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "MusicLibraryAgent/4.0 ( https://github.com/aruntito/MUSIC )"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
        if data:
            cache_file.write_bytes(data)
            return data
    except Exception:
        pass

    return None


def embed_artwork_in_file(audio_path: Path, image_data: bytes) -> bool:
    """
    Embed JPEG image_data into audio file tags using mutagen.
    Supports MP3 (ID3 APIC), M4A (covr), FLAC (PICTURE).
    Does NOT re-encode audio — tag write only.
    Returns True on success, False on failure.
    """
    import mutagen  # noqa: PLC0415
    from mutagen.id3 import ID3, APIC, ID3NoHeaderError  # noqa: PLC0415

    audio_path = Path(audio_path)
    ext = audio_path.suffix.lower()

    try:
        if ext == ".mp3":
            try:
                tags = ID3(str(audio_path))
            except ID3NoHeaderError:
                tags = ID3()
            # Remove existing APIC frames then add new one
            tags.delall("APIC")
            tags.add(APIC(
                encoding=3,       # UTF-8
                mime="image/jpeg",
                type=3,           # Cover (front)
                desc="Cover",
                data=image_data,
            ))
            tags.save(str(audio_path))
            return True

        elif ext == ".m4a":
            from mutagen.mp4 import MP4, MP4Cover  # noqa: PLC0415
            audio = MP4(str(audio_path))
            if audio.tags is None:
                audio.add_tags()
            audio.tags["covr"] = [MP4Cover(image_data, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
            return True

        elif ext == ".flac":
            from mutagen.flac import FLAC, Picture  # noqa: PLC0415
            audio = FLAC(str(audio_path))
            pic = Picture()
            pic.type = 3          # Cover (front)
            pic.mime = "image/jpeg"
            pic.desc = "Cover"
            pic.data = image_data
            audio.clear_pictures()
            audio.add_picture(pic)
            audio.save()
            return True

        elif ext in (".ogg", ".oga"):
            from mutagen.oggvorbis import OggVorbis  # noqa: PLC0415
            import base64  # noqa: PLC0415
            from mutagen.flac import Picture  # noqa: PLC0415
            audio = OggVorbis(str(audio_path))
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.desc = "Cover"
            pic.data = image_data
            audio["metadata_block_picture"] = [
                base64.b64encode(pic.write()).decode("ascii")
            ]
            audio.save()
            return True

    except Exception:
        pass

    return False


def save_folder_jpg(image_data: bytes, artist_dir: Path) -> Optional[Path]:
    """
    Save artwork as folder.jpg in the given artist directory.
    Returns the saved path or None on failure.
    """
    dest = Path(artist_dir) / "folder.jpg"
    try:
        dest.write_bytes(image_data)
        return dest
    except IOError:
        return None


def apply_artwork(
    audio_path: Path,
    image_data: bytes,
    mode: str = DEFAULT_MODE,
) -> dict:
    """
    Apply artwork to an audio file according to the selected mode.

    Args:
        audio_path: Path to the audio file at destination.
        image_data: Raw JPEG bytes of the artwork.
        mode: One of MODE_EMBED, MODE_FOLDER_JPG, MODE_BOTH.

    Returns:
        dict with keys:
          - "embedded": bool
          - "folder_jpg": Optional[Path]
    """
    result = {"embedded": False, "folder_jpg": None}

    if not image_data:
        return result

    if mode in (MODE_EMBED, MODE_BOTH):
        result["embedded"] = embed_artwork_in_file(audio_path, image_data)

    if mode in (MODE_FOLDER_JPG, MODE_BOTH):
        artist_dir = audio_path.parent
        result["folder_jpg"] = save_folder_jpg(image_data, artist_dir)

    return result
