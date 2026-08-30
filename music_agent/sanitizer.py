"""
Filename and path sanitizer for macOS, Android, and cross-platform compatibility.
"""

import re
import unicodedata
from pathlib import Path

# Characters forbidden on Windows, Android (FAT32/exFAT), and macOS POSIX
# / \ : * ? " < > | and control characters (0x00-0x1f)
INVALID_CHARS_PATTERN = re.compile(r'[/\\:*?"<>|\x00-\x1f]')
REDUNDANT_SPACES_PATTERN = re.compile(r'\s+')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}


def sanitize_filename(name: str, max_length: int = 180) -> str:
    """
    Sanitize a filename (base name or name with extension) for safe storage on macOS,
    Android, and external FAT32/exFAT storage drives.
    """
    if not name:
        return "Unknown"

    # Normalize Unicode (NFC for macOS/Linux compatibility)
    normalized = unicodedata.normalize("NFC", str(name))

    # Replace illegal characters with spaces or underscores
    cleaned = INVALID_CHARS_PATTERN.sub(" ", normalized)

    # Collapse multiple spaces
    cleaned = REDUNDANT_SPACES_PATTERN.sub(" ", cleaned)
    cleaned = cleaned.strip(" ._")

    if not cleaned:
        cleaned = "Unknown"

    # Handle reserved names on FAT/NTFS
    base_check = cleaned.split(".")[0].upper()
    if base_check in RESERVED_NAMES:
        cleaned = f"_{cleaned}"

    # Handle length constraints while preserving extension
    if len(cleaned) > max_length:
        path = Path(cleaned)
        ext = path.suffix
        stem = path.stem
        allowed_stem_len = max(1, max_length - len(ext))
        cleaned = f"{stem[:allowed_stem_len].strip()}{ext}"

    return cleaned


def sanitize_folder_path(rel_path: str) -> str:
    """
    Sanitize relative subfolder components (e.g. 'International/Billie Eilish').
    """
    parts = Path(rel_path).parts
    sanitized_parts = [sanitize_filename(part) for part in parts if part and part != "."]
    return "/".join(sanitized_parts)
