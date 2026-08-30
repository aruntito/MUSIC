"""
Legitimate Music Acquisition Discovery and Staging Engine.
Strictly non-destructive, respects DRM/licensing, enforces SSRF/domain policy,
and delegates library execution exclusively to the centralized Organizer pipeline.
"""

import csv
from dataclasses import dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
import time
from typing import List, Dict, Optional, Tuple

from music_agent.config import LibraryConfig
from music_agent.connectors.base import (
    BaseConnector,
    TrackCandidate,
    AcquisitionSourceStatus,
    AcquisitionPolicy,
    validate_acquisition_url,
)
from music_agent.connectors.manual import ManualLocalConnector
from music_agent.connectors.official_stores import OfficialStoreConnector
from music_agent.connectors.public_archive import PublicArchiveConnector
from music_agent.inventory import WishlistManager, WishlistTrack
from music_agent.organizer import LibraryOrganizer, FileAction, ActionType


@dataclass
class TrackAcquisitionResult:
    track: WishlistTrack
    status: AcquisitionSourceStatus
    candidate: Optional[TrackCandidate] = None
    all_candidates: List[TrackCandidate] = field(default_factory=list)
    action: Optional[FileAction] = None
    message: str = ""
    error_detail: Optional[str] = None


@dataclass
class AcquisitionReport:
    total_requested: int = 0
    available_count: int = 0
    purchase_required_count: int = 0
    stream_only_count: int = 0
    unavailable_count: int = 0
    acquired_count: int = 0
    dry_run: bool = True
    results: List[TrackAcquisitionResult] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    duration_seconds: float = 0.0


class AcquisitionManager:
    def __init__(
        self,
        config: LibraryConfig,
        wishlist_path: Optional[Path] = None,
        acquisition_config_path: Optional[Path] = None,
    ):
        self.config = config
        self.wishlist_manager = WishlistManager(config, wishlist_path=wishlist_path)
        self.organizer = LibraryOrganizer(config)

        if acquisition_config_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            acquisition_config_path = base_dir / "config" / "acquisition.json"
        self.acquisition_config_path = Path(acquisition_config_path).expanduser().resolve()
        self.raw_config = self._load_config()
        self.policy = self._build_policy()

        # Initialize connectors respecting config toggles
        self.connectors: List[BaseConnector] = []
        conn_cfg = self.raw_config.get("connectors", {})

        if conn_cfg.get("manual_local", {}).get("enabled", True):
            self.connectors.append(ManualLocalConnector(self.policy))

        if conn_cfg.get("official_stores", {}).get("enabled", True):
            self.connectors.append(OfficialStoreConnector())

        if conn_cfg.get("public_archives", {}).get("enabled", True):
            self.connectors.append(PublicArchiveConnector())

    def _load_config(self) -> dict:
        if self.acquisition_config_path.exists():
            with open(self.acquisition_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _build_policy(self) -> AcquisitionPolicy:
        settings = self.raw_config.get("settings", {})
        return AcquisitionPolicy(
            allowed_schemes=settings.get("allowed_schemes", ["file", "https"]),
            trusted_direct_domains=settings.get(
                "trusted_direct_domains",
                ["bandcamp.com", "archive.org", "freemusicarchive.org", "jamendo.com"]
            ),
            timeout_seconds=int(settings.get("timeout_seconds", 15)),
            max_download_size_bytes=int(settings.get("max_download_size_bytes", 262144000)),
            block_private_ips=bool(settings.get("block_private_ips", True)),
        )

    def discover_track_candidates(self, track: WishlistTrack) -> List[TrackCandidate]:
        """Discover legitimate acquisition candidates for a track across enabled connectors."""
        candidates: List[TrackCandidate] = []

        # 1. Check user-supplied explicit source_url in wishlist
        if track.source_url:
            manual_conn = ManualLocalConnector(self.policy)
            test_cand = TrackCandidate(
                source_name="WishlistSourceUrl",
                artist=track.artist,
                title=track.title,
                status=AcquisitionSourceStatus.AVAILABLE,
                direct_download_url=track.source_url,
            )
            is_policy_ok = manual_conn.verify_policy_compliance(test_cand)
            status = AcquisitionSourceStatus.AVAILABLE if is_policy_ok else AcquisitionSourceStatus.UNAVAILABLE
            reason = "User-supplied source URL passed domain/scheme policy" if is_policy_ok else "User-supplied source failed domain/scheme policy"

            candidates.append(TrackCandidate(
                source_name="WishlistSourceUrl",
                artist=track.artist,
                title=track.title,
                status=status,
                direct_download_url=track.source_url if is_policy_ok else None,
                reason=reason,
                is_policy_approved=is_policy_ok,
            ))

        # 2. Query enabled connectors
        for conn in self.connectors:
            try:
                results = conn.search(track.artist, track.title)
                candidates.extend(results)
            except Exception as e:
                print(f"[WARNING] Connector {conn.source_name} search error: {e}")

        if not candidates:
            candidates.append(
                TrackCandidate(
                    source_name="None",
                    artist=track.artist,
                    title=track.title,
                    status=AcquisitionSourceStatus.UNAVAILABLE,
                    reason="No verified legitimate digital source discovered",
                    is_policy_approved=False,
                )
            )

        return candidates

    def run_acquisition(
        self,
        dry_run: bool = True,
        artist_filter: Optional[str] = None,
        title_filter: Optional[str] = None,
    ) -> AcquisitionReport:
        """
        Run discovery and (if dry_run=False) legitimate staging for missing wishlist tracks.
        """
        inv_report = self.wishlist_manager.scan_inventory()
        missing_items = [item for item in inv_report.items if not item.found]

        if artist_filter:
            missing_items = [i for i in missing_items if artist_filter.lower() in i.track.artist.lower()]
        if title_filter:
            missing_items = [i for i in missing_items if title_filter.lower() in i.track.title.lower()]

        report = AcquisitionReport(
            total_requested=len(missing_items),
            dry_run=dry_run,
            start_time=time.time(),
        )

        for item in missing_items:
            track = item.track
            candidates = self.discover_track_candidates(track)

            chosen_candidate = None
            for cand in candidates:
                if cand.status == AcquisitionSourceStatus.AVAILABLE and cand.is_policy_approved:
                    chosen_candidate = cand
                    break
            if not chosen_candidate:
                for cand in candidates:
                    if cand.status == AcquisitionSourceStatus.PURCHASE_REQUIRED:
                        chosen_candidate = cand
                        break
            if not chosen_candidate:
                chosen_candidate = candidates[0]

            res = TrackAcquisitionResult(
                track=track,
                status=chosen_candidate.status,
                candidate=chosen_candidate,
                all_candidates=candidates,
            )

            if chosen_candidate.status == AcquisitionSourceStatus.AVAILABLE and chosen_candidate.is_policy_approved:
                report.available_count += 1
                if not dry_run:
                    self._execute_staging_and_import(chosen_candidate, res)
                    if res.action and res.action.executed:
                        report.acquired_count += 1
                else:
                    res.message = f"Downloadable file candidate from policy-approved source ({chosen_candidate.source_name})"
            elif chosen_candidate.status == AcquisitionSourceStatus.PURCHASE_REQUIRED:
                report.purchase_required_count += 1
                store_info = f" ({chosen_candidate.store_url})" if chosen_candidate.store_url else ""
                res.message = f"Official digital purchase search generated: {chosen_candidate.source_name}{store_info}"
            elif chosen_candidate.status == AcquisitionSourceStatus.STREAM_ONLY:
                report.stream_only_count += 1
                res.message = "Streaming only; no DRM-free downloadable file available"
            else:
                report.unavailable_count += 1
                res.message = chosen_candidate.reason or "Unavailable"

            report.results.append(res)

        report.duration_seconds = time.time() - report.start_time
        return report

    def _execute_staging_and_import(self, candidate: TrackCandidate, result: TrackAcquisitionResult):
        """Stage a policy-approved track into a temporary directory and pass to Organizer pipeline."""
        with tempfile.TemporaryDirectory(prefix="music_agent_acq_") as temp_stage_dir:
            staging_path = Path(temp_stage_dir)
            manual_conn = ManualLocalConnector(self.policy)
            staged_file = manual_conn.stage_track(candidate, staging_path)

            if not staged_file or not staged_file.exists():
                result.error_detail = "Failed to stage policy-approved file (download failed or rejected)"
                result.message = "Staging failed"
                return

            action = self.organizer.plan_file(staged_file)
            action = self.organizer.execute_action(action)
            result.action = action

            if action.executed:
                result.message = f"Successfully staged and imported to {action.target_path.name}"
            else:
                result.message = f"Organizer action: {action.message}"
                result.error_detail = action.error_detail

    def generate_reports(self, report: AcquisitionReport, output_dir: Optional[Path] = None) -> Tuple[Path, Path]:
        """Generate reports/acquisition_report.md and reports/acquisition_candidates.csv."""
        if output_dir is None:
            output_dir = Path.cwd() / "reports"
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        md_file = output_dir / "acquisition_report.md"
        csv_file = output_dir / "acquisition_candidates.csv"

        mode_str = "Dry-Run Discovery" if report.dry_run else "Acquisition Run"

        # 1. CSV Report
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Artist", "Title", "Category", "Status", "Source",
                "Format", "Quality", "Policy_Approved", "Purchase_Search_URL", "Download_URL", "Notes"
            ])
            for r in report.results:
                cand = r.candidate
                writer.writerow([
                    r.track.artist,
                    r.track.title,
                    r.track.category,
                    r.status.value,
                    cand.source_name if cand else "None",
                    cand.format if cand else "",
                    cand.bitrate_or_quality if cand else "",
                    "Yes" if (cand and cand.is_policy_approved) else "No",
                    cand.store_url or "" if cand else "",
                    cand.direct_download_url or "" if (cand and cand.is_policy_approved) else "",
                    r.message,
                ])

        # 2. Markdown Report
        md_lines = [
            f"# Music Library Agent - {mode_str} Report",
            "",
            f"- **Date & Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"- **Mode**: `{'Dry-Run Preview (No downloads performed)' if report.dry_run else 'Live Acquisition (Policy-Approved Direct Sources Only)'}`",
            f"- **Processing Time**: {report.duration_seconds:.3f} seconds",
            "",
            "## Summary Statistics",
            "",
            "| Metric | Count | Description |",
            "| :--- | :---: | :--- |",
            f"| **Missing Tracks Evaluated** | **{report.total_requested}** | Tracks from wishlist not yet present in library |",
            f"| **Policy-Approved Free/Direct Downloads** | **{report.available_count}** | Legitimate direct download files from trusted sources |",
            f"| **Official Store Purchase Search Options** | **{report.purchase_required_count}** | Commercial tracks with generated store search links |",
            f"| **Stream Only (No DRM-free files)** | **{report.stream_only_count}** | Streaming platform only |",
            f"| **Unavailable / Unknown** | **{report.unavailable_count}** | No legitimate source found |",
            f"| **Successfully Staged & Imported** | **{report.acquired_count}** | Live imported tracks |",
            "",
            "## Acquisition Candidates by Track",
            "",
            "| # | Artist | Title | Status | Source | Format / Quality | Legitimate Destination / Purchase Search |",
            "| :---: | :--- | :--- | :---: | :--- | :--- | :--- |",
        ]

        for idx, r in enumerate(report.results, start=1):
            cand = r.candidate
            status_badge = {
                AcquisitionSourceStatus.AVAILABLE: "🟢 `AVAILABLE`",
                AcquisitionSourceStatus.PURCHASE_REQUIRED: "🟡 `PURCHASE_REQUIRED`",
                AcquisitionSourceStatus.STREAM_ONLY: "⚪ `STREAM_ONLY`",
                AcquisitionSourceStatus.UNAVAILABLE: "🔴 `UNAVAILABLE`",
            }.get(r.status, "`UNKNOWN`")

            source_str = cand.source_name if cand else "None"
            fmt_str = f"{cand.format or ''} ({cand.bitrate_or_quality or ''})".strip() if cand else "-"
            if fmt_str == "()":
                fmt_str = "-"

            link_str = "-"
            if cand and cand.store_url:
                link_str = f"[Store Search Link]({cand.store_url})"
            elif cand and cand.direct_download_url and cand.is_policy_approved:
                link_str = f"`{cand.direct_download_url}`"
            elif r.message:
                link_str = r.message

            art_safe = r.track.artist.replace("|", "\\|")
            tit_safe = r.track.title.replace("|", "\\|")

            md_lines.append(f"| {idx} | {art_safe} | {tit_safe} | {status_badge} | {source_str} | {fmt_str} | {link_str} |")

        md_lines.extend([
            "",
            "## Licensing & DRM Protection Policy",
            "- No copyrighted commercial music was scraped, ripped from streams, or downloaded without authorization.",
            "- Tracks classified as `PURCHASE_REQUIRED` must be purchased legally through official stores.",
            "- Only verified direct downloads from trusted domains are processed into temporary staging and the Organizer pipeline.",
            ""
        ])

        with open(md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return md_file, csv_file
