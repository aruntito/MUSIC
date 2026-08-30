"""
Wishlist and Inventory Engine.
Compares curated wishlist tracks against local library and reports missing/acquired songs.
"""

import csv
from dataclasses import dataclass, field, asdict
from datetime import datetime
import json
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple

from music_agent.config import LibraryConfig
from music_agent.matcher import normalize_string
from music_agent.metadata import read_audio_metadata


@dataclass
class WishlistTrack:
    artist: str
    title: str
    category: str
    priority: str = "core"
    status: str = "wanted"  # "wanted", "acquired", "unavailable"
    album: Optional[str] = None
    year: Optional[int] = None
    duration: Optional[str] = None
    source_url: Optional[str] = None


@dataclass
class InventoryItem:
    track: WishlistTrack
    found: bool = False
    local_path: Optional[Path] = None
    duplicate_paths: List[Path] = field(default_factory=list)


@dataclass
class InventoryReport:
    total_requested: int = 0
    found_locally_count: int = 0
    missing_count: int = 0
    duplicates_count: int = 0
    unknown_local_count: int = 0
    items: List[InventoryItem] = field(default_factory=list)
    unknown_local_files: List[Path] = field(default_factory=list)


class WishlistManager:
    def __init__(self, config: LibraryConfig, wishlist_path: Optional[Path] = None):
        self.config = config
        if wishlist_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            wishlist_path = base_dir / "config" / "wishlist.json"
        self.wishlist_path = Path(wishlist_path).expanduser().resolve()

    def load_and_validate(self) -> List[WishlistTrack]:
        """Load wishlist and validate against approved library rules."""
        if not self.wishlist_path.exists():
            raise FileNotFoundError(f"Wishlist file not found: {self.wishlist_path}")

        with open(self.wishlist_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict) or "tracks" not in data:
            raise ValueError("Invalid wishlist schema: root must contain 'tracks' list")

        tracks_raw = data.get("tracks", [])
        validated_tracks: List[WishlistTrack] = []
        seen_keys: Set[Tuple[str, str]] = set()

        for idx, t in enumerate(tracks_raw, start=1):
            if not isinstance(t, dict):
                raise ValueError(f"Track #{idx} must be a JSON object")

            artist = t.get("artist", "").strip()
            title = t.get("title", "").strip()
            category = t.get("category", "").strip()
            priority = t.get("priority", "core").strip()
            status = t.get("status", "wanted").strip()

            if not artist or not title or not category:
                raise ValueError(f"Track #{idx} is missing required fields (artist, title, category)")

            # Validate that artist belongs to the approved 44 artists
            artist_norm = normalize_string(artist)
            matched_rule = None
            for art_key, rule in self.config.artists.items():
                if normalize_string(rule.canonical_name) == artist_norm or artist_norm in [normalize_string(a) for a in rule.aliases]:
                    matched_rule = rule
                    break

            if not matched_rule:
                raise ValueError(f"Track #{idx}: Artist '{artist}' is not in approved 44 artists in library_rules.json")

            # Check duplicate wishlist entries
            track_key = (artist_norm, normalize_string(title))
            if track_key in seen_keys:
                raise ValueError(f"Duplicate entry in wishlist: '{artist} - {title}'")
            seen_keys.add(track_key)

            validated_tracks.append(WishlistTrack(
                artist=matched_rule.canonical_name,
                title=title,
                category=category,
                priority=priority,
                status=status,
                album=t.get("album"),
                year=t.get("year"),
                duration=t.get("duration"),
                source_url=t.get("source_url"),
            ))

        return validated_tracks

    def scan_inventory(self, destination_dir: Optional[Path] = None) -> InventoryReport:
        """Scan destination library and compare against wishlist tracks."""
        tracks = self.load_and_validate()
        dest = (destination_dir or self.config.destination_dir).resolve()

        report = InventoryReport(total_requested=len(tracks))
        local_files: List[Path] = []

        if dest.exists():
            for p in dest.rglob("*"):
                if p.is_file() and p.suffix.lower() in self.config.supported_extensions and not p.name.startswith("."):
                    local_files.append(p)

        # Index local library by normalized (artist, title)
        local_index: Dict[Tuple[str, str], List[Path]] = {}
        for f in local_files:
            meta = read_audio_metadata(f)
            art = meta.artist or ""
            tit = meta.title or f.stem
            key = (normalize_string(art), normalize_string(tit))
            local_index.setdefault(key, []).append(f)

        matched_local_paths: Set[Path] = set()

        for track in tracks:
            t_key = (normalize_string(track.artist), normalize_string(track.title))
            if t_key in local_index and len(local_index[t_key]) > 0:
                found_paths = local_index[t_key]
                primary_path = found_paths[0]
                dup_paths = found_paths[1:]
                matched_local_paths.update(found_paths)

                report.found_locally_count += 1
                if dup_paths:
                    report.duplicates_count += len(dup_paths)

                report.items.append(InventoryItem(
                    track=track,
                    found=True,
                    local_path=primary_path,
                    duplicate_paths=dup_paths,
                ))
            else:
                report.missing_count += 1
                report.items.append(InventoryItem(
                    track=track,
                    found=False,
                ))

        # Identify unknown local files
        for f in local_files:
            if f not in matched_local_paths:
                report.unknown_local_files.append(f)
        report.unknown_local_count = len(report.unknown_local_files)

        return report

    def generate_reports(self, report: InventoryReport, output_dir: Optional[Path] = None) -> Tuple[Path, Path, Path]:
        """Generate library_inventory.json, missing.csv, and inventory_report.md."""
        if output_dir is None:
            output_dir = Path.cwd() / "reports"
        output_dir = Path(output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        json_file = output_dir / "library_inventory.json"
        csv_file = output_dir / "missing.csv"
        md_file = output_dir / "inventory_report.md"

        # 1. library_inventory.json
        json_data = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "requested": report.total_requested,
                "found_locally": report.found_locally_count,
                "missing": report.missing_count,
                "duplicates": report.duplicates_count,
                "unknown_local": report.unknown_local_count,
            },
            "tracks": [
                {
                    "artist": item.track.artist,
                    "title": item.track.title,
                    "category": item.track.category,
                    "priority": item.track.priority,
                    "status": "acquired" if item.found else item.track.status,
                    "found": item.found,
                    "local_path": str(item.local_path) if item.local_path else None,
                    "duplicates": [str(d) for d in item.duplicate_paths],
                }
                for item in report.items
            ],
            "unknown_local_files": [str(f) for f in report.unknown_local_files]
        }
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2)

        # 2. missing.csv
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Artist", "Title", "Category", "Priority", "Status"])
            for item in report.items:
                if not item.found:
                    writer.writerow([
                        item.track.artist,
                        item.track.title,
                        item.track.category,
                        item.track.priority,
                        item.track.status,
                    ])

        # 3. inventory_report.md
        md_lines = [
            "# Music Library Inventory Report",
            "",
            f"- **Date & Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary Statistics",
            "",
            "| Metric | Count | Description |",
            "| :--- | :---: | :--- |",
            f"| **Requested (Wishlist)** | **{report.total_requested}** | Curated wishlist tracks |",
            f"| **Found Locally** | **{report.found_locally_count}** | Acquired tracks in destination library |",
            f"| **Missing** | **{report.missing_count}** | Wishlist tracks awaiting acquisition |",
            f"| **Duplicates in Library** | **{report.duplicates_count}** | Multiple copies detected in library |",
            f"| **Unknown Local Files** | **{report.unknown_local_count}** | Local files not on official wishlist |",
            "",
            "## Missing Tracks Inventory",
            "",
            "| # | Artist | Title | Category | Priority | Status |",
            "| :---: | :--- | :--- | :--- | :---: | :---: |",
        ]

        missing_items = [item for item in report.items if not item.found]
        if not missing_items:
            md_lines.append("| - | *None* | *All requested tracks are present in library!* | - | - | - |")
        else:
            for idx, item in enumerate(missing_items, start=1):
                art_safe = item.track.artist.replace("|", "\\|")
                tit_safe = item.track.title.replace("|", "\\|")
                md_lines.append(f"| {idx} | {art_safe} | {tit_safe} | {item.track.category} | {item.track.priority} | `{item.track.status}` |")

        if report.unknown_local_files:
            md_lines.extend([
                "",
                "## Unknown Local Files (Not in Wishlist)",
                "",
                "| # | File Path |",
                "| :---: | :--- |",
            ])
            for idx, uf in enumerate(report.unknown_local_files, start=1):
                md_lines.append(f"| {idx} | `{str(uf)}` |")

        with open(md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        return json_file, csv_file, md_file
