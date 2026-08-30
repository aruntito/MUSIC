"""
Duplicate detection and SHA-256 indexing for idempotent library management.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Dict, Optional, Set


def compute_file_sha256(file_path: Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file efficiently using chunking."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest()


@dataclass
class DuplicateInfo:
    is_duplicate: bool
    existing_path: Optional[Path] = None
    reason: Optional[str] = None


class DuplicateDetector:
    def __init__(self, destination_dir: Path, review_dir: Path, supported_exts: Set[str]):
        self.destination_dir = destination_dir
        self.review_dir = review_dir
        self.supported_exts = supported_exts
        # Map: sha256 -> Path
        self._hash_to_path: Dict[str, Path] = {}
        # Map: normalized target relative path -> sha256
        self._target_path_index: Dict[str, str] = {}
        self._scanned = False

    def scan_existing_destination(self):
        """Scan destination and review directory to index existing audio files."""
        if self._scanned:
            return
        for root_dir in [self.destination_dir, self.review_dir]:
            if not root_dir.exists():
                continue
            for file_path in root_dir.rglob("*"):
                if file_path.is_file() and file_path.suffix.lower() in self.supported_exts:
                    try:
                        file_hash = compute_file_sha256(file_path)
                        self._hash_to_path[file_hash] = file_path
                        self._target_path_index[str(file_path.resolve())] = file_hash
                    except (IOError, PermissionError):
                        continue
        self._scanned = True

    def check_file(self, source_path: Path, target_path: Path, source_hash: Optional[str] = None) -> DuplicateInfo:
        """
        Check if source file is a duplicate of:
        1. An existing file in destination/review by SHA-256
        2. A target file path already occupied by the same or different file
        """
        if not source_hash:
            source_hash = compute_file_sha256(source_path)

        # 1. Exact SHA-256 match in destination / review or earlier in current run
        if source_hash in self._hash_to_path:
            existing = self._hash_to_path[source_hash]
            return DuplicateInfo(
                is_duplicate=True,
                existing_path=existing,
                reason=f"Identical file content already exists at '{existing.name}' (SHA-256 match)"
            )

        # 2. Target path collision check
        target_resolved_str = str(target_path.resolve())
        if target_path.exists():
            target_hash = compute_file_sha256(target_path)
            if target_hash == source_hash:
                return DuplicateInfo(
                    is_duplicate=True,
                    existing_path=target_path,
                    reason=f"Target file already exists with identical content"
                )
            else:
                return DuplicateInfo(
                    is_duplicate=True,
                    existing_path=target_path,
                    reason=f"Collision: Target file exists with different content"
                )

        return DuplicateInfo(is_duplicate=False)

    def register_imported(self, file_hash: str, target_path: Path):
        """Register a newly planned or copied file in the deduplicator index."""
        self._hash_to_path[file_hash] = target_path
        self._target_path_index[str(target_path.resolve())] = file_hash
