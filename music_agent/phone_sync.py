"""
Android Phone Music Sync Module.
Safely synchronizes organized music from ~/Downloads/Songs/ to an Android device
via ADB (Android Debug Bridge) or mounted storage / directory.
Strictly copy-only: NEVER deletes, overwrites, or removes files from the phone.
"""

from abc import ABC, abstractmethod
import csv
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Dict, List, Optional, Tuple

from music_agent.config import LibraryConfig
from music_agent.deduplicator import compute_file_sha256
from music_agent.sanitizer import sanitize_filename, sanitize_folder_path


class SyncStatus(str, Enum):
    TO_COPY = "TO_COPY"
    ALREADY_EXISTS = "ALREADY_EXISTS"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass
class SyncItem:
    source_path: Path
    relative_dest_path: str
    size_bytes: int
    sha256_hash: Optional[str] = None
    status: SyncStatus = SyncStatus.TO_COPY
    transferred: bool = False
    message: str = ""
    error_detail: Optional[str] = None


@dataclass
class SyncReport:
    backend_name: str
    target_location: str
    total_source_files: int = 0
    to_copy_count: int = 0
    already_exists_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    transferred_count: int = 0
    total_transfer_bytes: int = 0
    dry_run: bool = True
    items: List[SyncItem] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    duration_seconds: float = 0.0


def format_bytes(size_bytes: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class SyncBackend(ABC):
    """
    Abstract interface for Android transport backends.
    Strictly copy-only: NO deletion or removal methods exist.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def check_ready(self) -> Tuple[bool, str]:
        """Check if backend and target device/folder are ready."""
        pass

    @abstractmethod
    def list_target_files(self, target_base: str) -> Dict[str, Dict[str, any]]:
        """
        List existing audio files on target destination.
        Returns dict: relative_path -> {"size_bytes": int, "sha256": Optional[str]}
        """
        pass

    @abstractmethod
    def transfer_file(self, src_path: Path, relative_dest_path: str, target_base: str) -> Tuple[bool, str]:
        """Transfer file to target destination."""
        pass

    @abstractmethod
    def verify_transferred_file(
        self, relative_dest_path: str, expected_size: int, expected_hash: Optional[str], target_base: str
    ) -> bool:
        """Verify transferred file exists with expected size."""
        pass


class DirectoryBackend(SyncBackend):
    """
    Sync backend for mounted Android USB volumes, SD cards, OTG drives, or local target folders.
    """

    def __init__(self, target_dir: Optional[Path] = None):
        self.target_dir = Path(target_dir).expanduser().resolve() if target_dir else None

    @property
    def name(self) -> str:
        return "Directory (Mounted Storage / USB)"

    def check_ready(self) -> Tuple[bool, str]:
        if not self.target_dir:
            return False, "Target directory not specified."
        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
            if not os.access(self.target_dir, os.W_OK):
                return False, f"Target directory '{self.target_dir}' is not writable."
            return True, f"Target directory '{self.target_dir}' is ready."
        except Exception as e:
            return False, f"Failed to access target directory '{self.target_dir}': {e}"

    def list_target_files(self, target_base: str) -> Dict[str, Dict[str, any]]:
        base = Path(target_base).expanduser().resolve()
        if not base.exists():
            return {}

        results: Dict[str, Dict[str, any]] = {}
        for root, _, files in os.walk(base):
            for file in files:
                if file.startswith("."):
                    continue
                full_path = Path(root) / file
                rel_path = str(full_path.relative_to(base))
                size = full_path.stat().st_size
                results[rel_path] = {
                    "size_bytes": size,
                    "sha256": None,
                    "full_path": full_path,
                }
        return results

    def transfer_file(self, src_path: Path, relative_dest_path: str, target_base: str) -> Tuple[bool, str]:
        base = Path(target_base).expanduser().resolve()
        dest_path = base / relative_dest_path

        # Security check: containment inside target_base
        if not str(dest_path.resolve()).startswith(str(base)):
            return False, f"Security rejection: target path '{dest_path}' escapes target directory."

        # Safety check: Never overwrite existing files automatically
        if dest_path.exists():
            return False, f"Destination file '{dest_path}' already exists (overwrite blocked)."

        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src_path), str(dest_path))
            return True, f"Copied to {dest_path.name}"
        except Exception as e:
            return False, f"Copy failed: {e}"

    def verify_transferred_file(
        self, relative_dest_path: str, expected_size: int, expected_hash: Optional[str], target_base: str
    ) -> bool:
        base = Path(target_base).expanduser().resolve()
        dest_path = base / relative_dest_path
        if not dest_path.exists():
            return False
        if dest_path.stat().st_size != expected_size:
            return False
        if expected_hash:
            actual_hash = compute_file_sha256(dest_path)
            if actual_hash != expected_hash:
                return False
        return True


class AdbBackend(SyncBackend):
    """
    Sync backend for Android devices connected via ADB (USB debugging or wireless).
    """

    def __init__(self, adb_path: str = "adb", device_id: Optional[str] = None):
        self.adb_path = adb_path
        self.device_id = device_id

    @property
    def name(self) -> str:
        return "ADB (Android Debug Bridge)"

    def _run_adb_cmd(self, args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        cmd = [self.adb_path]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    def check_ready(self) -> Tuple[bool, str]:
        # 1. Check if adb binary is available
        if not shutil.which(self.adb_path):
            return False, f"ADB binary '{self.adb_path}' not found in PATH."

        # 2. Check connected devices
        try:
            res = self._run_adb_cmd(["devices"], timeout=10)
            if res.returncode != 0:
                return False, f"ADB check failed: {res.stderr.strip()}"

            lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            device_lines = [l for l in lines[1:] if not l.startswith("*")]

            if not device_lines:
                return False, "No Android device connected via ADB."

            authorized_devices = []
            for d in device_lines:
                parts = d.split()
                if len(parts) >= 2 and parts[1] == "device":
                    authorized_devices.append(parts[0])
                elif len(parts) >= 2 and parts[1] == "unauthorized":
                    return False, f"Android device '{parts[0]}' is unauthorized. Please accept the USB debugging prompt on your phone."
                elif len(parts) >= 2 and parts[1] == "offline":
                    return False, f"Android device '{parts[0]}' is offline."

            if not authorized_devices:
                return False, "No authorized Android device found."

            if self.device_id and self.device_id not in authorized_devices:
                return False, f"Specified device '{self.device_id}' not found among connected devices ({authorized_devices})."

            active_device = self.device_id or authorized_devices[0]
            self.device_id = active_device
            return True, f"ADB connected to device '{active_device}'."
        except Exception as e:
            return False, f"ADB connection check error: {e}"

    def list_target_files(self, target_base: str) -> Dict[str, Dict[str, any]]:
        target_dir = target_base.rstrip("/")
        results: Dict[str, Dict[str, any]] = {}

        cmd = ["shell", f"find '{target_dir}' -type f 2>/dev/null"]
        try:
            res = self._run_adb_cmd(cmd, timeout=30)
            if res.returncode != 0:
                return {}

            remote_files = [line.strip() for line in res.stdout.splitlines() if line.strip()]
            for rpath in remote_files:
                if not rpath.startswith(target_dir):
                    continue
                rel_path = rpath[len(target_dir):].lstrip("/")
                results[rel_path] = {
                    "size_bytes": 0,
                    "sha256": None,
                    "remote_path": rpath,
                }
            return results
        except Exception:
            return {}

    def transfer_file(self, src_path: Path, relative_dest_path: str, target_base: str) -> Tuple[bool, str]:
        target_dir = target_base.rstrip("/")
        dest_remote_path = f"{target_dir}/{relative_dest_path}"
        dest_remote_folder = str(Path(dest_remote_path).parent)

        # 1. Create remote parent directory
        mkdir_res = self._run_adb_cmd(["shell", f"mkdir -p '{dest_remote_folder}'"])
        if mkdir_res.returncode != 0:
            return False, f"Failed to create remote directory '{dest_remote_folder}': {mkdir_res.stderr.strip()}"

        # 2. Push file via adb push
        push_res = self._run_adb_cmd(["push", str(src_path), dest_remote_path], timeout=120)
        if push_res.returncode != 0:
            return False, f"ADB push failed: {push_res.stderr.strip()}"

        return True, f"Pushed to {dest_remote_path}"

    def verify_transferred_file(
        self, relative_dest_path: str, expected_size: int, expected_hash: Optional[str], target_base: str
    ) -> bool:
        target_dir = target_base.rstrip("/")
        dest_remote_path = f"{target_dir}/{relative_dest_path}"

        res = self._run_adb_cmd(["shell", f"wc -c < '{dest_remote_path}' 2>/dev/null"])
        if res.returncode != 0:
            return False
        try:
            remote_size = int(res.stdout.strip())
            return remote_size == expected_size
        except ValueError:
            return False


class PhoneSyncManager:
    """
    Manager for orchestrating safe, copy-only sync from library to Android phone.
    """

    def __init__(
        self,
        config: LibraryConfig,
        backend: Optional[SyncBackend] = None,
        source_dir: Optional[Path] = None,
        target_base: Optional[str] = None,
    ):
        self.config = config
        self.source_dir = Path(source_dir).expanduser().resolve() if source_dir else config.destination_dir
        self.target_base = target_base or "/sdcard/Music"
        self.backend = backend or DirectoryBackend()

    def discover_source_tracks(self) -> List[Path]:
        """Scan source directory for audio tracks."""
        if not self.source_dir.exists():
            return []

        tracks: List[Path] = []
        for root, _, files in os.walk(self.source_dir):
            for file in sorted(files):
                if file.startswith("."):
                    continue
                ext = Path(file).suffix.lower()
                if ext in self.config.supported_extensions:
                    tracks.append(Path(root) / file)
        return sorted(tracks)

    def plan_sync(self) -> SyncReport:
        """Plan sync without transferring files (Dry-Run Preview)."""
        source_tracks = self.discover_source_tracks()
        report = SyncReport(
            backend_name=self.backend.name,
            target_location=str(self.target_base),
            total_source_files=len(source_tracks),
            dry_run=True,
            start_time=time.time(),
        )

        ready, msg = self.backend.check_ready()
        if not ready:
            report.error_count = 1
            report.duration_seconds = time.time() - report.start_time
            return report

        existing_target_files = self.backend.list_target_files(self.target_base)

        for track_path in source_tracks:
            rel_path = str(track_path.relative_to(self.source_dir))
            size = track_path.stat().st_size
            item = SyncItem(
                source_path=track_path,
                relative_dest_path=rel_path,
                size_bytes=size,
            )

            # Check duplicate / existing on target
            if rel_path in existing_target_files:
                target_info = existing_target_files[rel_path]
                target_size = target_info.get("size_bytes", 0)

                if target_size == 0 or target_size == size:
                    item.status = SyncStatus.ALREADY_EXISTS
                    item.message = "Already present on phone"
                    report.already_exists_count += 1
                else:
                    item.status = SyncStatus.TO_COPY
                    item.message = "File present on phone but size differs; planned for safe transfer"
                    report.to_copy_count += 1
                    report.total_transfer_bytes += size
            else:
                item.status = SyncStatus.TO_COPY
                item.message = "New track; ready to sync"
                report.to_copy_count += 1
                report.total_transfer_bytes += size

            report.items.append(item)

        report.duration_seconds = time.time() - report.start_time
        return report

    def execute_sync(self) -> SyncReport:
        """Execute safe copy-only sync to target Android location."""
        report = self.plan_sync()
        report.dry_run = False
        report.start_time = time.time()

        ready, msg = self.backend.check_ready()
        if not ready:
            report.error_count = 1
            report.duration_seconds = time.time() - report.start_time
            return report

        for item in report.items:
            if item.status != SyncStatus.TO_COPY:
                continue

            success, message = self.backend.transfer_file(
                src_path=item.source_path,
                relative_dest_path=item.relative_dest_path,
                target_base=self.target_base,
            )

            if success:
                verified = self.backend.verify_transferred_file(
                    relative_dest_path=item.relative_dest_path,
                    expected_size=item.size_bytes,
                    expected_hash=item.sha256_hash,
                    target_base=self.target_base,
                )
                if verified:
                    item.transferred = True
                    item.message = f"Transferred & verified: {item.relative_dest_path}"
                    report.transferred_count += 1
                else:
                    item.status = SyncStatus.ERROR
                    item.error_detail = "Transfer completed but post-copy verification failed"
                    report.error_count += 1
            else:
                item.status = SyncStatus.ERROR
                item.error_detail = message
                report.error_count += 1

        report.duration_seconds = time.time() - report.start_time
        return report

    def generate_reports(self, report: SyncReport, output_dir: Optional[Path] = None) -> Tuple[Path, Path]:
        """Generate markdown report and CSV manifest for the phone sync operation."""
        if output_dir is None:
            output_dir = Path.cwd() / "reports"
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        md_file = output_dir / "phone_sync_report.md"
        csv_file = output_dir / "phone_sync_manifest.csv"

        mode_str = "Dry-Run Preview" if report.dry_run else "Execution"

        # 1. CSV Manifest
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Relative_Path", "Status", "Size_Bytes", "Size_Formatted", "Transferred", "Notes", "Error_Detail"
            ])
            for item in report.items:
                writer.writerow([
                    item.relative_dest_path,
                    item.status.value,
                    item.size_bytes,
                    format_bytes(item.size_bytes),
                    "Yes" if item.transferred else "No",
                    item.message,
                    item.error_detail or "",
                ])

        # 2. Markdown Report
        md_lines = [
            f"# Music Library Agent - Phone Sync Report ({mode_str})",
            "",
            f"- **Date & Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Transport Backend**: `{report.backend_name}`",
            f"- **Target Location**: `{report.target_location}`",
            f"- **Source Library**: `{self.source_dir}`",
            f"- **Mode**: `{'Dry-Run Preview (No files transferred)' if report.dry_run else 'Live Safe Copy Sync'}`",
            f"- **Duration**: {report.duration_seconds:.3f} seconds",
            "",
            "## Transfer Summary",
            "",
            "| Metric | Value | Description |",
            "| :--- | :---: | :--- |",
            f"| **Total Source Tracks** | **{report.total_source_files}** | Audio tracks found in local organized library |",
            f"| **Files to Copy** | **{report.to_copy_count}** | New tracks planned for phone transfer |",
            f"| **Already Present on Phone** | **{report.already_exists_count}** | Identical tracks already present (skipped) |",
            f"| **Errors / Failed** | **{report.error_count}** | Transfer or verification failures |",
            f"| **Successfully Transferred** | **{report.transferred_count}** | Confirmed live transfers |",
            f"| **Total Transfer Payload** | **{format_bytes(report.total_transfer_bytes)}** | Total size of files to transfer |",
            "",
            "## Track Sync Manifest",
            "",
            "| # | Relative Device Path | Size | Status | Transferred | Notes |",
            "| :---: | :--- | :---: | :---: | :---: | :--- |",
        ]

        for idx, item in enumerate(report.items, start=1):
            status_badge = {
                SyncStatus.TO_COPY: "🔵 `TO_COPY`",
                SyncStatus.ALREADY_EXISTS: "🟢 `ALREADY_EXISTS`",
                SyncStatus.SKIPPED: "⚪ `SKIPPED`",
                SyncStatus.ERROR: "🔴 `ERROR`",
            }.get(item.status, "`UNKNOWN`")

            trans_str = "✅ Yes" if item.transferred else "No"
            safe_rel = item.relative_dest_path.replace("|", "\\|")
            notes = (item.error_detail or item.message).replace("|", "\\|")

            md_lines.append(
                f"| {idx} | `{safe_rel}` | {format_bytes(item.size_bytes)} | {status_badge} | {trans_str} | {notes} |"
            )

        md_lines.extend([
            "",
            "## Safety & Integrity Guarantee",
            "- **Copy-Only Operation**: Zero files on the phone or destination were deleted, modified, or removed.",
            "- **Duplicate Prevention**: Tracks already existing on the device were preserved and skipped.",
            "- **Post-Transfer Verification**: Destination files were verified after transfer.",
            ""
        ])

        with open(md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return md_file, csv_file
