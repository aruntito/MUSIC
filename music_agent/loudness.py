"""
ReplayGain / Loudness Analysis using FFmpeg EBU R128 loudnorm filter.

NEVER re-encodes audio. Analysis only + optional tag write via mutagen.
Requires: ffmpeg (already installed at /opt/homebrew/bin/ffmpeg)

Usage:
    result = analyze_loudness(Path("song.mp3"))
    if result:
        write_replaygain_tags(Path("song.mp3"), result)

CLI:
    music-agent analyze [--path <dir>] [--write-tags]
"""

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

SUPPORTED_AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".ogg"}
TARGET_LUFS = -18.0         # Standard ReplayGain target (EBU R128 at -23 LUFS is broadcast; -18 is music common)
REFERENCE_LUFS = -18.0


@dataclass
class LoudnessInfo:
    """EBU R128 loudness measurement for a single track."""
    file_path: Path
    integrated_lufs: float      # LUFS-I (Integrated Loudness)
    true_peak_dbfs: float       # dBTP (True Peak)
    lra_lu: float               # LRA (Loudness Range)
    replaygain_gain_db: float   # calculated gain in dB (positive = need to boost)
    replaygain_peak: float      # linear peak value (0.0–1.0+)


def _find_ffmpeg() -> Optional[str]:
    """Locate ffmpeg binary. Checks common macOS Homebrew paths first."""
    for candidate in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg"]:
        if Path(candidate).exists():
            return candidate
    return shutil.which("ffmpeg")


def analyze_loudness(file_path: Path, ffmpeg_path: Optional[str] = None) -> Optional[LoudnessInfo]:
    """
    Analyze a single audio file using FFmpeg's EBU R128 loudnorm filter.
    Returns LoudnessInfo or None if analysis fails or ffmpeg is unavailable.

    This performs ANALYSIS ONLY — no re-encoding, no file modification.
    """
    ffmpeg = ffmpeg_path or _find_ffmpeg()
    if not ffmpeg:
        return None

    file_path = Path(file_path).resolve()
    if not file_path.exists() or file_path.suffix.lower() not in SUPPORTED_AUDIO_EXTS:
        return None

    # ffmpeg loudnorm in analysis mode: pass=1 outputs JSON stats to stderr
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i", str(file_path),
        "-af", "loudnorm=I=-18:TP=-1:LRA=11:print_format=json",
        "-f", "null",
        "-",
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        stderr_text = result.stderr.decode("utf-8", errors="replace")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None

    # Extract JSON block from stderr output
    json_match = re.search(r'\{[^{}]+\}', stderr_text, re.DOTALL)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return None

    def _safe_float(key: str, default: float = 0.0) -> float:
        val = data.get(key, default)
        try:
            f = float(val)
            return f if f not in (float("inf"), float("-inf")) else default
        except (TypeError, ValueError):
            return default

    integrated = _safe_float("input_i")
    true_peak = _safe_float("input_tp")
    lra = _safe_float("input_lra")

    # ReplayGain = target - measured integrated loudness
    gain_db = TARGET_LUFS - integrated

    # Convert true peak from dBTP to linear for REPLAYGAIN_TRACK_PEAK tag
    import math  # noqa: PLC0415
    try:
        peak_linear = 10 ** (true_peak / 20.0)
    except (ValueError, OverflowError):
        peak_linear = 1.0

    return LoudnessInfo(
        file_path=file_path,
        integrated_lufs=integrated,
        true_peak_dbfs=true_peak,
        lra_lu=lra,
        replaygain_gain_db=round(gain_db, 2),
        replaygain_peak=round(peak_linear, 6),
    )


def write_replaygain_tags(file_path: Path, info: LoudnessInfo) -> bool:
    """
    Write REPLAYGAIN_TRACK_GAIN and REPLAYGAIN_TRACK_PEAK tags to audio file.
    Uses mutagen — NO audio re-encoding.
    Returns True on success, False on failure.
    """
    import mutagen  # noqa: PLC0415
    from mutagen.id3 import ID3, TXXX, ID3NoHeaderError  # noqa: PLC0415

    file_path = Path(file_path).resolve()
    ext = file_path.suffix.lower()
    gain_str = f"{info.replaygain_gain_db:+.2f} dB"
    peak_str = f"{info.replaygain_peak:.6f}"

    try:
        if ext == ".mp3":
            try:
                tags = ID3(str(file_path))
            except ID3NoHeaderError:
                tags = ID3()
            # Remove any existing RG frames
            for key in list(tags.keys()):
                if "REPLAYGAIN" in key.upper():
                    del tags[key]
            tags.add(TXXX(encoding=3, desc="REPLAYGAIN_TRACK_GAIN", text=gain_str))
            tags.add(TXXX(encoding=3, desc="REPLAYGAIN_TRACK_PEAK", text=peak_str))
            tags.save(str(file_path))
            return True

        elif ext == ".flac":
            from mutagen.flac import FLAC  # noqa: PLC0415
            audio = FLAC(str(file_path))
            audio["REPLAYGAIN_TRACK_GAIN"] = gain_str
            audio["REPLAYGAIN_TRACK_PEAK"] = peak_str
            audio.save()
            return True

        elif ext == ".m4a":
            from mutagen.mp4 import MP4  # noqa: PLC0415
            audio = MP4(str(file_path))
            if audio.tags is None:
                audio.add_tags()
            audio.tags["----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN"] = [
                gain_str.encode("utf-8")
            ]
            audio.tags["----:com.apple.iTunes:REPLAYGAIN_TRACK_PEAK"] = [
                peak_str.encode("utf-8")
            ]
            audio.save()
            return True

        elif ext in (".ogg", ".oga"):
            from mutagen.oggvorbis import OggVorbis  # noqa: PLC0415
            audio = OggVorbis(str(file_path))
            audio["REPLAYGAIN_TRACK_GAIN"] = [gain_str]
            audio["REPLAYGAIN_TRACK_PEAK"] = [peak_str]
            audio.save()
            return True

    except Exception:
        pass

    return False


def analyze_directory(
    directory: Path,
    write_tags: bool = False,
    ffmpeg_path: Optional[str] = None,
) -> list:
    """
    Analyze all audio files in a directory recursively.
    Returns list of LoudnessInfo results.
    """
    directory = Path(directory).resolve()
    results = []

    for audio_file in sorted(directory.rglob("*")):
        if not audio_file.is_file():
            continue
        if audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTS:
            continue
        if audio_file.name.startswith("."):
            continue

        info = analyze_loudness(audio_file, ffmpeg_path=ffmpeg_path)
        if info:
            results.append(info)
            if write_tags:
                write_replaygain_tags(audio_file, info)

    return results
