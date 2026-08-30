"""
Music Library Organizer and Pipeline Execution Engine.
Strictly copy-only, non-destructive, and idempotent.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import shutil
import time
from typing import List, Optional

from music_agent.config import LibraryConfig
from music_agent.deduplicator import DuplicateDetector, compute_file_sha256
from music_agent.matcher import ArtistMatcher, MatchResult
from music_agent.metadata import AudioMetadata, read_audio_metadata
from music_agent.sanitizer import sanitize_filename, sanitize_folder_path


class ActionType(str, Enum):
    IMPORT = "IMPORT"
    DUPLICATE = "DUPLICATE"
    REVIEW = "REVIEW"
    MISSING_METADATA = "MISSING_METADATA"
    ERROR = "ERROR"


@dataclass
class FileAction:
    source_path: Path
    target_path: Optional[Path]
    action_type: ActionType
    metadata: Optional[AudioMetadata] = None
    match_result: Optional[MatchResult] = None
    file_hash: Optional[str] = None
    message: str = ""
    error_detail: Optional[str] = None
    executed: bool = False


@dataclass
class PipelineReport:
    total_scanned: int = 0
    imported_count: int = 0
    duplicate_count: int = 0
    unmatched_count: int = 0
    missing_metadata_count: int = 0
    error_count: int = 0
    actions: List[FileAction] = field(default_factory=list)
    dry_run: bool = True
    start_time: float = field(default_factory=time.time)
    duration_seconds: float = 0.0


class LibraryOrganizer:
    def __init__(self, config: LibraryConfig):
        self.config = config
        self.matcher = ArtistMatcher(config)
        self.deduplicator = DuplicateDetector(
            destination_dir=config.destination_dir,
            review_dir=config.review_dir,
            supported_exts=config.supported_extensions,
        )

    def scan_inbox(self, source_dir: Optional[Path] = None) -> List[Path]:
        """Scan source inbox recursively for supported audio files."""
        src = (source_dir or self.config.source_dir).resolve()
        if not src.exists():
            return []

        audio_files = []
        for p in src.rglob("*"):
            if p.is_file() and p.suffix.lower() in self.config.supported_extensions:
                if not p.name.startswith("."):
                    audio_files.append(p)
        return sorted(audio_files)

    def plan_file(self, file_path: Path) -> FileAction:
        """Plan the processing action for a single audio file."""
        try:
            file_hash = compute_file_sha256(file_path)
            meta = read_audio_metadata(file_path)
            ext = file_path.suffix.lower()

            missing_meta = not meta.has_embedded_metadata

            # Match artist
            match = self.matcher.match(meta)

            if match.matched:
                artist_name = match.canonical_artist or meta.artist or "Unknown Artist"
                title_name = meta.title or file_path.stem

                # Format filename: {artist} - {title}.ext
                formatted_name = self.config.file_naming_format.format(
                    artist=artist_name,
                    title=title_name,
                    ext=ext.lstrip(".")
                )
                safe_filename = sanitize_filename(formatted_name, self.config.max_filename_length)
                target_subfolder = sanitize_folder_path(match.target_subfolder or "Uncategorized")
                target_path = self.config.destination_dir / target_subfolder / safe_filename

                # Duplicate detection check
                dup_info = self.deduplicator.check_file(file_path, target_path, source_hash=file_hash)
                if dup_info.is_duplicate:
                    return FileAction(
                        source_path=file_path,
                        target_path=target_path,
                        action_type=ActionType.DUPLICATE,
                        metadata=meta,
                        match_result=match,
                        file_hash=file_hash,
                        message=f"Duplicate skipped: {dup_info.reason}",
                    )

                # Register in deduplicator so other files in same batch don't collide
                self.deduplicator.register_imported(file_hash, target_path)

                action_type = ActionType.IMPORT
                msg = f"Import -> {match.target_subfolder}/{safe_filename}"
                if missing_meta:
                    msg += " (Fallback filename metadata used)"

                return FileAction(
                    source_path=file_path,
                    target_path=target_path,
                    action_type=action_type,
                    metadata=meta,
                    match_result=match,
                    file_hash=file_hash,
                    message=msg,
                )

            else:
                # Unmatched -> Route safely to Review directory
                fallback_artist = meta.artist or "Unknown Artist"
                fallback_title = meta.title or file_path.stem
                formatted_name = f"{fallback_artist} - {fallback_title}{ext}"
                safe_filename = sanitize_filename(formatted_name, self.config.max_filename_length)
                target_path = self.config.review_dir / safe_filename

                dup_info = self.deduplicator.check_file(file_path, target_path, source_hash=file_hash)
                if dup_info.is_duplicate:
                    return FileAction(
                        source_path=file_path,
                        target_path=target_path,
                        action_type=ActionType.DUPLICATE,
                        metadata=meta,
                        match_result=match,
                        file_hash=file_hash,
                        message=f"Duplicate in Review skipped: {dup_info.reason}",
                    )

                self.deduplicator.register_imported(file_hash, target_path)

                action_type = ActionType.MISSING_METADATA if (not meta.artist and not meta.title) else ActionType.REVIEW
                return FileAction(
                    source_path=file_path,
                    target_path=target_path,
                    action_type=action_type,
                    metadata=meta,
                    match_result=match,
                    file_hash=file_hash,
                    message=f"Unmatched artist -> Route to Review/ ({match.reason or 'Unmatched'})",
                )

        except Exception as e:
            return FileAction(
                source_path=file_path,
                target_path=None,
                action_type=ActionType.ERROR,
                message=f"Error inspecting file: {str(e)}",
                error_detail=str(e),
            )

    def execute_action(self, action: FileAction) -> FileAction:
        """
        Execute a planned copy action safely:
        1. Ensure destination directory exists
        2. Copy file bit-for-bit (copy2 preserves metadata)
        3. Verify SHA-256 integrity after copy
        4. Update deduplication index
        Original file remains completely untouched.
        """
        if action.action_type not in (ActionType.IMPORT, ActionType.REVIEW, ActionType.MISSING_METADATA):
            return action

        if action.target_path is None:
            action.action_type = ActionType.ERROR
            action.error_detail = "Target path is missing for execution"
            action.message = "Execution failed: No target path"
            return action

        try:
            # Ensure target parent directory exists
            action.target_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file safely without modifying or moving original
            shutil.copy2(str(action.source_path), str(action.target_path))

            # Perform post-copy SHA-256 integrity check
            copied_hash = compute_file_sha256(action.target_path)
            if copied_hash != action.file_hash:
                # Remove corrupted copy immediately
                try:
                    action.target_path.unlink()
                except OSError:
                    pass
                action.action_type = ActionType.ERROR
                action.error_detail = "Integrity check failed: Copied file hash does not match original"
                action.message = "Integrity verification failed!"
                action.executed = False
            else:
                action.executed = True
                if action.file_hash:
                    self.deduplicator.register_imported(action.file_hash, action.target_path)

        except Exception as copy_err:
            action.action_type = ActionType.ERROR
            action.error_detail = str(copy_err)
            action.message = f"Copy failed: {str(copy_err)}"
            action.executed = False

        return action

    def process(self, dry_run: bool = True, source_dir: Optional[Path] = None) -> PipelineReport:
        """
        Execute full pipeline:
        1. Index existing destination to guarantee idempotency
        2. Scan inbox
        3. Plan actions for all files
        4. In dry-run mode: return plan summary
        5. In live mode: execute actions via execute_action()
        """
        report = PipelineReport(dry_run=dry_run, start_time=time.time())

        self.deduplicator.scan_existing_destination()
        files_to_process = self.scan_inbox(source_dir)
        report.total_scanned = len(files_to_process)

        for file_path in files_to_process:
            action = self.plan_file(file_path)

            if not dry_run:
                action = self.execute_action(action)

            # Aggregate statistics
            if action.action_type == ActionType.IMPORT:
                report.imported_count += 1
                if action.metadata and not action.metadata.has_embedded_metadata:
                    report.missing_metadata_count += 1
            elif action.action_type == ActionType.DUPLICATE:
                report.duplicate_count += 1
            elif action.action_type in (ActionType.REVIEW, ActionType.MISSING_METADATA):
                report.unmatched_count += 1
                if action.action_type == ActionType.MISSING_METADATA:
                    report.missing_metadata_count += 1
            elif action.action_type == ActionType.ERROR:
                report.error_count += 1

            report.actions.append(action)

        report.duration_seconds = time.time() - report.start_time
        return report
