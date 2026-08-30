"""
Acoustic fingerprinting for duplicate detection using AcoustID / Chromaprint.

Optional enhancement: requires `fpcalc` binary (brew install chromaprint).
Falls back to SHA-256 + metadata-based detection gracefully if fpcalc is unavailable.

Policy: REPORTS duplicates only — never auto-deletes or auto-overwrites.
"""

import hashlib
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

SUPPORTED_AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".wav", ".ogg"}


@dataclass
class FingerprintResult:
    file_path: Path
    fingerprint: Optional[str] = None  # AcoustID fingerprint string
    duration_seconds: Optional[float] = None
    method: str = "sha256"  # "acoustid" or "sha256"


@dataclass
class DuplicateGroup:
    """A group of files identified as probable duplicates."""
    canonical_path: Path              # Representative (first-seen) file
    duplicates: List[Path] = field(default_factory=list)
    method: str = "sha256"           # detection method used
    confidence: str = "exact"        # "exact" | "probable"
    note: str = ""


def _find_fpcalc() -> Optional[str]:
    """Locate fpcalc binary (Chromaprint)."""
    for candidate in ["/opt/homebrew/bin/fpcalc", "/usr/local/bin/fpcalc"]:
        if Path(candidate).exists():
            return candidate
    return shutil.which("fpcalc")


def compute_acoustid_fingerprint(file_path: Path, fpcalc_path: Optional[str] = None) -> Optional[FingerprintResult]:
    """
    Compute AcoustID fingerprint for a file using fpcalc.
    Returns None if fpcalc is not available or the file is unsupported.
    """
    fpcalc = fpcalc_path or _find_fpcalc()
    if not fpcalc:
        return None

    file_path = Path(file_path).resolve()
    if not file_path.exists():
        return None

    try:
        result = subprocess.run(
            [fpcalc, "-json", str(file_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=60,
        )
        import json  # noqa: PLC0415
        data = json.loads(result.stdout.decode("utf-8", errors="replace"))
        return FingerprintResult(
            file_path=file_path,
            fingerprint=data.get("fingerprint"),
            duration_seconds=data.get("duration"),
            method="acoustid",
        )
    except Exception:
        return None


def compute_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def find_duplicates(
    directory: Path,
    use_acoustid: bool = True,
    fpcalc_path: Optional[str] = None,
) -> List[DuplicateGroup]:
    """
    Find duplicate audio files in directory using SHA-256 (always) and
    optionally AcoustID fingerprinting (if fpcalc is available).

    Returns list of DuplicateGroup — advisory report only, NO deletion.
    """
    directory = Path(directory).resolve()
    if not directory.exists():
        return []

    # Collect all audio files
    audio_files: List[Path] = [
        f for f in sorted(directory.rglob("*"))
        if f.is_file() and f.suffix.lower() in SUPPORTED_AUDIO_EXTS and not f.name.startswith(".")
    ]

    # --- SHA-256 exact duplicate detection ---
    sha256_map: Dict[str, Path] = {}
    exact_groups: List[DuplicateGroup] = []
    exact_dupe_set: Set[Path] = set()

    for audio_file in audio_files:
        try:
            h = compute_sha256(audio_file)
        except (IOError, PermissionError):
            continue

        if h in sha256_map:
            canonical = sha256_map[h]
            # Find existing group or create new one
            found = False
            for g in exact_groups:
                if g.canonical_path == canonical:
                    g.duplicates.append(audio_file)
                    found = True
                    break
            if not found:
                exact_groups.append(DuplicateGroup(
                    canonical_path=canonical,
                    duplicates=[audio_file],
                    method="sha256",
                    confidence="exact",
                    note="Identical file content (SHA-256)",
                ))
            exact_dupe_set.add(audio_file)
        else:
            sha256_map[h] = audio_file

    # --- AcoustID fingerprint duplicate detection (optional) ---
    acoustid_groups: List[DuplicateGroup] = []
    fpcalc = (_find_fpcalc() if use_acoustid else None) or (fpcalc_path if use_acoustid else None)

    if fpcalc:
        fp_map: Dict[str, Path] = {}
        for audio_file in audio_files:
            if audio_file in exact_dupe_set:
                continue  # Already caught by SHA-256
            fp_result = compute_acoustid_fingerprint(audio_file, fpcalc_path=fpcalc)
            if not fp_result or not fp_result.fingerprint:
                continue
            fp = fp_result.fingerprint
            if fp in fp_map:
                canonical = fp_map[fp]
                found = False
                for g in acoustid_groups:
                    if g.canonical_path == canonical:
                        g.duplicates.append(audio_file)
                        found = True
                        break
                if not found:
                    acoustid_groups.append(DuplicateGroup(
                        canonical_path=canonical,
                        duplicates=[audio_file],
                        method="acoustid",
                        confidence="probable",
                        note="Same acoustic fingerprint (AcoustID/Chromaprint)",
                    ))
            else:
                fp_map[fp] = audio_file

    return exact_groups + acoustid_groups
