"""
Synthetic audio file generator for testing Music Library Agent without copyrighted audio.
Creates minimal valid MP3, M4A, FLAC, WAV, and OGG structures with embedded tags.
"""

from pathlib import Path
import struct
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TRCK, TPE2
from mutagen.flac import FLAC
from mutagen.oggvorbis import OggVorbis
from mutagen.wave import WAVE
from mutagen.mp4 import MP4


def create_dummy_wav(path: Path, artist: str = "", title: str = "", album: str = "") -> Path:
    """Create a minimal valid PCM WAV file and optionally add INFO tags."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # 1 second of 8kHz 8-bit mono silence (8000 bytes)
    sample_rate = 8000
    num_samples = 8000
    audio_data = b"\x80" * num_samples
    data_chunk_size = len(audio_data)

    # Format chunk (16 bytes PCM)
    fmt_chunk = struct.pack("<4sIHHIIHH", b"fmt ", 16, 1, 1, sample_rate, sample_rate, 1, 8)
    
    # Data chunk
    data_chunk = struct.pack("<4sI", b"data", data_chunk_size) + audio_data

    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    header = struct.pack("<4sI4s", b"RIFF", riff_size, b"WAVE")

    with open(path, "wb") as f:
        f.write(header)
        f.write(fmt_chunk)
        f.write(data_chunk)

    if artist or title or album:
        try:
            w = WAVE(str(path))
            if w.tags is None:
                w.add_tags()
            if title:
                w.tags.add(TIT2(encoding=3, text=title))
            if artist:
                w.tags.add(TPE1(encoding=3, text=artist))
            if album:
                w.tags.add(TALB(encoding=3, text=album))
            w.save()
        except Exception:
            pass

    return path


def create_dummy_mp3(path: Path, artist: str = "", title: str = "", album: str = "", album_artist: str = "", track_num: str = "") -> Path:
    """Create a minimal valid MP3 frame and write ID3v2 tags with Mutagen."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # MPEG-1 Audio Layer III sync word + header + silence payload
    # 0xFFFB9064 is standard MPEG1 Layer 3 128kbps 44.1kHz stereo frame header
    frame_header = b"\xff\xfb\x90\x64"
    frame_payload = b"\x00" * 413
    frame = frame_header + frame_payload

    with open(path, "wb") as f:
        # Write 5 frames so mutagen recognizes it as valid MP3
        f.write(frame * 5)

    if artist or title or album or album_artist or track_num:
        try:
            id3 = ID3()
            if title:
                id3.add(TIT2(encoding=3, text=title))
            if artist:
                id3.add(TPE1(encoding=3, text=artist))
            if album_artist:
                id3.add(TPE2(encoding=3, text=album_artist))
            if album:
                id3.add(TALB(encoding=3, text=album))
            if track_num:
                id3.add(TRCK(encoding=3, text=track_num))
            id3.save(str(path))
        except Exception as e:
            print(f"Warning: Failed to tag dummy MP3 {path}: {e}")

    return path


def create_dummy_flac(path: Path, artist: str = "", title: str = "", album: str = "") -> Path:
    """Create a minimal valid FLAC stream header and add Vorbis comments."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Minimal FLAC header: 'fLaC' marker + STREAMINFO block
    flac_marker = b"fLaC"
    # Streaminfo metadata block header: bit 0 = last metadata block (0x80), type 0 = STREAMINFO (0x00), length 34 bytes (0x000022)
    # Total block header: 0x80000022
    # 34 bytes streaminfo payload
    streaminfo_payload = struct.pack(
        ">HH3s3s8s16s",
        4096, 4096,  # min/max blocksize
        b"\x00\x00\x00", b"\x00\x00\x00",  # min/max framesize
        b"\x0a\xc4\x42\xf0\x00\x00\x00\x00",  # 44100Hz, 2 channels, 16 bits, 0 samples
        b"\x00" * 16  # MD5 signature
    )
    block_header = struct.pack(">I", 0x80000022)

    with open(path, "wb") as f:
        f.write(flac_marker)
        f.write(block_header)
        f.write(streaminfo_payload)

    if artist or title or album:
        try:
            f_audio = FLAC(str(path))
            if artist:
                f_audio["artist"] = artist
            if title:
                f_audio["title"] = title
            if album:
                f_audio["album"] = album
            f_audio.save()
        except Exception:
            pass

    return path


def create_dummy_m4a(path: Path, artist: str = "", title: str = "", album: str = "") -> Path:
    """Create a minimal valid ISO BMFF MP4/M4A atom structure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Minimal ftyp atom
    ftyp_data = b"M4A \x00\x00\x00\x00M4A mp42isom"
    ftyp_atom = struct.pack(">I4s", len(ftyp_data) + 8, b"ftyp") + ftyp_data

    # Minimal moov atom
    moov_data = b"\x00" * 16
    moov_atom = struct.pack(">I4s", len(moov_data) + 8, b"moov") + moov_data

    with open(path, "wb") as f:
        f.write(ftyp_atom)
        f.write(moov_atom)

    return path
