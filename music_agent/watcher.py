"""
Inbox and Downloads Folder Watcher.
Monitors configured folders for new audio files and ZIP archives.
Strictly copy-only, non-destructive, and prevents path traversal.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import List, Set, Optional, Dict
import zipfile

from music_agent.config import LibraryConfig
from music_agent.organizer import LibraryOrganizer, FileAction, ActionType


def is_safe_zip_member(target_dir: Path, member: zipfile.ZipInfo) -> bool:
    """
    Validate that a ZIP entry is safe to extract:
    - Rejects path traversal (Zip Slip, '..', absolute paths)
    - Rejects symlink members
    - Rejects nested ZIP archives (no recursive unpacking)
    """
    filename = member.filename
    # Check absolute path
    if filename.startswith("/") or filename.startswith("\\"):
        return False
    if ":" in filename:  # Windows drive letters or alternate streams
        return False

    # Check symlinks (UNIX mode in external_attr)
    mode = (member.external_attr >> 16) & 0o170000
    if mode == 0o120000:  # S_IFLNK
        return False

    # Path traversal check
    target_abs = target_dir.resolve()
    dest_abs = (target_dir / filename).resolve()
    try:
        common = os.path.commonpath([str(target_abs), str(dest_abs)])
        return common == str(target_abs)
    except (ValueError, OSError):
        return False


def extract_audio_from_zip(zip_path: Path, staging_dir: Path, supported_exts: Set[str]) -> List[Path]:
    """
    Safely inspect and extract only supported audio files from a ZIP archive.
    Rejects path traversal attacks and preserves original ZIP intact.
    Does NOT recursively extract nested archives.
    """
    extracted_files: List[Path] = []
    if not zipfile.is_zipfile(zip_path):
        return []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            if member.is_dir():
                continue

            member_name = member.filename
            ext = Path(member_name).suffix.lower()

            # Only extract direct supported audio files (ignore nested zips, txt, exe, etc.)
            if ext not in supported_exts or ext == ".zip":
                continue

            # Zip Slip security check
            if not is_safe_zip_member(staging_dir, member):
                print(f"[SECURITY WARNING] Rejected potentially malicious ZIP entry: {member_name}")
                continue

            # Extract safely with safe unique staging name
            safe_basename = Path(member_name).name
            target_path = staging_dir / safe_basename
            if target_path.exists():
                stem = Path(member_name).stem
                target_path = staging_dir / f"{stem}_{len(extracted_files)}{ext}"

            with zf.open(member) as src, open(target_path, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted_files.append(target_path)

    return extracted_files


@dataclass
class WatcherEvent:
    source_path: Path
    is_zip: bool
    actions: List[FileAction] = field(default_factory=list)


class FolderWatcher:
    def __init__(self, config: LibraryConfig, watch_dirs: Optional[List[Path]] = None):
        self.config = config
        default_dirs = [
            config.source_dir,
            Path(os.path.expanduser("~/Downloads")).resolve()
        ]
        self.watch_dirs = [Path(d).resolve() for d in (watch_dirs or default_dirs)]
        self.organizer = LibraryOrganizer(config)
        self.seen_files: Dict[Path, float] = {}  # Path -> mtime
        self.running = False

    def scan_new_items(self) -> List[Path]:
        """Scan watched directories for newly created or modified audio/zip files."""
        new_items: List[Path] = []
        for watch_dir in self.watch_dirs:
            if not watch_dir.exists():
                continue
            for p in watch_dir.iterdir():
                if p.name.startswith("."):
                    continue
                ext = p.suffix.lower()
                if ext in self.config.supported_extensions or ext == ".zip":
                    try:
                        mtime = p.stat().st_mtime
                        if p not in self.seen_files or self.seen_files[p] < mtime:
                            self.seen_files[p] = mtime
                            new_items.append(p)
                    except (IOError, OSError):
                        continue
        return new_items

    def process_item(self, item_path: Path, dry_run: bool = True) -> WatcherEvent:
        """
        Process a newly detected file or ZIP archive through the centralized Organizer pipeline.
        """
        ext = item_path.suffix.lower()
        if ext == ".zip":
            # Handle ZIP in temporary staging area
            with tempfile.TemporaryDirectory(prefix="music_agent_stage_") as temp_stage_dir:
                stage_path = Path(temp_stage_dir)
                extracted_audio = extract_audio_from_zip(item_path, stage_path, self.config.supported_extensions)
                event = WatcherEvent(source_path=item_path, is_zip=True)

                if not extracted_audio:
                    print(f"  [ZIP] No supported audio files found inside {item_path.name}")
                    return event

                print(f"  [ZIP] Extracted {len(extracted_audio)} audio file(s) from {item_path.name}")
                for audio_file in extracted_audio:
                    action = self.organizer.plan_file(audio_file)
                    if not dry_run:
                        action = self.organizer.execute_action(action)
                    event.actions.append(action)
                return event
        else:
            # Handle normal audio file
            action = self.organizer.plan_file(item_path)
            if not dry_run:
                action = self.organizer.execute_action(action)
            return WatcherEvent(source_path=item_path, is_zip=False, actions=[action])

    def run_loop(self, poll_interval: float = 2.0, dry_run: bool = True, max_cycles: Optional[int] = None):
        """Run the watcher poll loop with graceful Ctrl+C exit."""
        self.running = True
        mode_str = "DRY-RUN (Simulated Preview)" if dry_run else "LIVE (Copy-Only Import)"
        print("=" * 65)
        print(f"  MUSIC AGENT FOLDER WATCHER [{mode_str}]")
        print("=" * 65)
        print("  Watching directories:")
        for wd in self.watch_dirs:
            print(f"    - {wd}")
        print(f"  Poll interval: {poll_interval}s")
        if dry_run:
            print("  Note: Running in DRY-RUN mode. Use '--execute' for live import.")
        print("  Press Ctrl+C to stop.\n")

        # Initial baseline scan
        for watch_dir in self.watch_dirs:
            if watch_dir.exists():
                for p in watch_dir.iterdir():
                    try:
                        self.seen_files[p] = p.stat().st_mtime
                    except (IOError, OSError):
                        pass

        cycles = 0
        try:
            while self.running:
                new_items = self.scan_new_items()
                for item in new_items:
                    print(f"[{time.strftime('%H:%M:%S')}] Detected: {item.name}")
                    event = self.process_item(item, dry_run=dry_run)
                    for act in event.actions:
                        status_tag = f"[PLAN: {act.action_type.value}]" if dry_run else f"[{act.action_type.value}]"
                        print(f"       -> {status_tag} {act.message}")

                cycles += 1
                if max_cycles and cycles >= max_cycles:
                    break

                time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\n[INFO] Stopping watcher cleanly...")
        finally:
            self.running = False
            print("[INFO] Watcher stopped.")
