"""
Command Line Interface (CLI) for Music Library Agent.
"""

import argparse
import sys
from pathlib import Path

from music_agent.acquisition import AcquisitionManager
from music_agent.config import LibraryConfig
from music_agent.inventory import WishlistManager
from music_agent.metadata import read_audio_metadata
from music_agent.organizer import LibraryOrganizer
from music_agent.reporter import format_console_summary, generate_markdown_report
from music_agent.watcher import FolderWatcher


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="music-agent",
        description="Local Music Library Agent for macOS - Safe, copy-only music library organizer and classifier.",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Process and organize music from Inbox")
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Run in preview mode without copying any files (Default behavior)",
    )
    run_parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute live copy-import to destination and review folders",
    )
    run_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to library_rules.json configuration file",
    )
    run_parser.add_argument(
        "--source",
        "-s",
        type=str,
        default=None,
        help="Override source inbox directory (default: ~/Music/Inbox)",
    )
    run_parser.add_argument(
        "--dest",
        "-d",
        type=str,
        default=None,
        help="Override destination directory (default: ~/Downloads/Songs)",
    )
    run_parser.add_argument(
        "--review",
        "-r",
        type=str,
        default=None,
        help="Override review directory (default: ~/Music/Review)",
    )
    run_parser.add_argument(
        "--report-dir",
        type=str,
        default="reports",
        help="Directory to save timestamped markdown reports (default: ./reports)",
    )
    run_parser.add_argument(
        "--no-report",
        action="store_true",
        help="Do not save a Markdown report to disk",
    )

    # Command: inventory
    inv_parser = subparsers.add_parser("inventory", help="Compare wishlist against local library to track missing songs")
    inv_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to library_rules.json configuration file",
    )
    inv_parser.add_argument(
        "--wishlist",
        "-w",
        type=str,
        default=None,
        help="Path to wishlist.json file (default: config/wishlist.json)",
    )
    inv_parser.add_argument(
        "--dest",
        "-d",
        type=str,
        default=None,
        help="Override destination library directory (default: ~/Downloads/Songs)",
    )
    inv_parser.add_argument(
        "--report-dir",
        type=str,
        default="reports",
        help="Directory to save missing.csv and inventory reports (default: ./reports)",
    )

    # Command: acquire
    acq_parser = subparsers.add_parser("acquire", help="Discover legitimate acquisition paths and stage authorized downloads")
    acq_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Discover and report acquisition sources without downloading (Default behavior)",
    )
    acq_parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute download/staging for authorized available files only",
    )
    acq_parser.add_argument(
        "--artist",
        type=str,
        default=None,
        help="Filter acquisition to specific artist",
    )
    acq_parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Filter acquisition to specific song title",
    )
    acq_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to library_rules.json configuration file",
    )
    acq_parser.add_argument(
        "--wishlist",
        "-w",
        type=str,
        default=None,
        help="Path to wishlist.json file (default: config/wishlist.json)",
    )
    acq_parser.add_argument(
        "--dest",
        "-d",
        type=str,
        default=None,
        help="Override destination directory (default: ~/Downloads/Songs)",
    )
    acq_parser.add_argument(
        "--report-dir",
        type=str,
        default="reports",
        help="Directory to save acquisition reports (default: ./reports)",
    )

    # Command: watch
    watch_parser = subparsers.add_parser("watch", help="Watch Inbox and Downloads folders for new audio and ZIP files")
    watch_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview incoming files without copying (Default behavior)",
    )
    watch_parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute live copy-import on detected files",
    )
    watch_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to library_rules.json configuration file",
    )
    watch_parser.add_argument(
        "--watch-dir",
        type=str,
        action="append",
        default=None,
        help="Directory to watch (can be specified multiple times)",
    )
    watch_parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0)",
    )

    # Command: check-config
    cfg_parser = subparsers.add_parser("check-config", help="Verify and display configured artists and rules")
    cfg_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to library_rules.json configuration file",
    )

    # Command: inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect embedded metadata and match result for a single file")
    inspect_parser.add_argument("file", type=str, help="Path to audio file")
    inspect_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to library_rules.json configuration file",
    )

    return parser


def handle_run(args: argparse.Namespace) -> int:
    config = LibraryConfig.load(args.config)

    if args.source:
        config.source_dir = Path(args.source).expanduser().resolve()
    if args.dest:
        config.destination_dir = Path(args.dest).expanduser().resolve()
    if args.review:
        config.review_dir = Path(args.review).expanduser().resolve()

    if args.dry_run and args.execute:
        print("[ERROR] Cannot specify both '--dry-run' and '--execute'. Choose one.", file=sys.stderr)
        return 1

    dry_run = True
    if args.execute:
        dry_run = False
    elif not args.dry_run:
        print("\n[INFO] No mode specified. Defaulting to --dry-run for safety.")
        print("       Run with '--execute' to perform actual file copy.\n")
        dry_run = True

    print(f"Source Inbox:      {config.source_dir}")
    print(f"Destination:       {config.destination_dir}")
    print(f"Review Folder:     {config.review_dir}")
    print(f"Mode:              {'DRY-RUN PREVIEW' if dry_run else 'LIVE COPY-IMPORT'}")
    print("Scanning...")

    organizer = LibraryOrganizer(config)
    report = organizer.process(dry_run=dry_run)

    summary_text = format_console_summary(report)
    print(summary_text)

    if not args.no_report:
        report_file = generate_markdown_report(report, Path(args.report_dir))
        print(f"\n[✓] Detailed report saved to: {report_file}")

    if dry_run and report.total_scanned > 0:
        print("\nTo perform the copy import, run:")
        print("  python3 music_agent_cli.py run --execute")

    return 0 if report.error_count == 0 else 1


def handle_inventory(args: argparse.Namespace) -> int:
    try:
        config = LibraryConfig.load(args.config)
        if args.dest:
            config.destination_dir = Path(args.dest).expanduser().resolve()

        manager = WishlistManager(config, wishlist_path=args.wishlist)
        dest_dir = config.destination_dir

        print("=" * 60)
        print("  MUSIC LIBRARY INVENTORY SCAN")
        print("=" * 60)
        print(f"  Wishlist File:       {manager.wishlist_path}")
        print(f"  Destination Library: {dest_dir}")
        print("Scanning library...")

        report = manager.scan_inventory(destination_dir=dest_dir)
        json_file, csv_file, md_file = manager.generate_reports(report, output_dir=Path(args.report_dir))

        print("\n" + "=" * 60)
        print("  INVENTORY SUMMARY")
        print("=" * 60)
        print(f"  Requested (Wishlist):  {report.total_requested}")
        print(f"  Found Locally:         {report.found_locally_count}")
        print(f"  Missing:               {report.missing_count}")
        print(f"  Duplicates in Library: {report.duplicates_count}")
        print(f"  Unknown Local Files:   {report.unknown_local_count}")
        print("=" * 60)
        print(f"  [✓] JSON Inventory: {json_file}")
        print(f"  [✓] Missing CSV:    {csv_file}")
        print(f"  [✓] Full MD Report: {md_file}")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"[ERROR] Inventory scan failed: {e}", file=sys.stderr)
        return 1


def handle_acquire(args: argparse.Namespace) -> int:
    try:
        config = LibraryConfig.load(args.config)
        if args.dest:
            config.destination_dir = Path(args.dest).expanduser().resolve()

        if args.dry_run and args.execute:
            print("[ERROR] Cannot specify both '--dry-run' and '--execute'. Choose one.", file=sys.stderr)
            return 1

        dry_run = True
        if args.execute:
            dry_run = False
        else:
            if not args.dry_run:
                print("\n[INFO] No acquisition mode specified. Defaulting to DRY-RUN preview for safety.")
                print("       Run with '--execute' to perform authorized downloads.\n")
            dry_run = True

        acq_mgr = AcquisitionManager(config, wishlist_path=args.wishlist)
        print("=" * 65)
        print(f"  MUSIC ACQUISITION DISCOVERY [{'DRY-RUN PREVIEW' if dry_run else 'LIVE ACQUISITION'}]")
        print("=" * 65)
        print("Discovering legitimate acquisition sources...")

        report = acq_mgr.run_acquisition(
            dry_run=dry_run,
            artist_filter=args.artist,
            title_filter=args.title,
        )
        md_file, csv_file = acq_mgr.generate_reports(report, output_dir=Path(args.report_dir))

        print("\n" + "=" * 65)
        print("  ACQUISITION SUMMARY")
        print("=" * 65)
        print(f"  Missing Tracks Evaluated:        {report.total_requested}")
        print(f"  Authorized Free/Direct Available: {report.available_count}")
        print(f"  Official Store Purchase Required: {report.purchase_required_count}")
        print(f"  Stream Only (No DRM-free files): {report.stream_only_count}")
        print(f"  Unavailable / Unknown:           {report.unavailable_count}")
        if not dry_run:
            print(f"  Successfully Acquired & Imported: {report.acquired_count}")
        print("=" * 65)
        print(f"  [✓] Acquisition Report:     {md_file}")
        print(f"  [✓] Candidates Spreadsheet: {csv_file}")
        print("=" * 65)
        return 0
    except Exception as e:
        print(f"[ERROR] Acquisition discovery failed: {e}", file=sys.stderr)
        return 1


def handle_watch(args: argparse.Namespace) -> int:
    try:
        config = LibraryConfig.load(args.config)
        watch_dirs = [Path(d).expanduser().resolve() for d in args.watch_dir] if args.watch_dir else None

        if args.dry_run and args.execute:
            print("[ERROR] Cannot specify both '--dry-run' and '--execute'. Choose one.", file=sys.stderr)
            return 1

        dry_run = True
        if args.execute:
            dry_run = False
        else:
            if not args.dry_run:
                print("\n[INFO] No watcher mode specified. Defaulting to DRY-RUN preview for safety.")
                print("       Run with '--execute' for live copy-import.\n")
            dry_run = True

        watcher = FolderWatcher(config, watch_dirs=watch_dirs)
        watcher.run_loop(poll_interval=args.poll_interval, dry_run=dry_run)
        return 0
    except Exception as e:
        print(f"[ERROR] Watcher error: {e}", file=sys.stderr)
        return 1


def handle_check_config(args: argparse.Namespace) -> int:
    try:
        config = LibraryConfig.load(args.config)
        print("=" * 60)
        print("  LIBRARY CONFIGURATION SUMMARY")
        print("=" * 60)
        print(f"  Source Inbox:        {config.source_dir}")
        print(f"  Destination Root:    {config.destination_dir}")
        print(f"  Review Directory:    {config.review_dir}")
        print(f"  Naming Format:       {config.file_naming_format}")
        print(f"  Sanitize Filenames:  {config.sanitize_filenames}")
        print(f"  Supported Exts:      {', '.join(sorted(config.supported_extensions))}")
        print(f"  Configured Artists:  {len(config.artists)}")
        print("=" * 60)
        print("  Categories & Artists:")

        cats = config.raw_config.get("categories", {})
        for cat_key, cat_val in cats.items():
            print(f"\n  [{cat_key}] (Template: {cat_val.get('folder_template')})")
            for art in cat_val.get("artists", []):
                aliases_str = f" (aliases: {', '.join(art.get('aliases', []))})" if art.get("aliases") else ""
                print(f"    - {art.get('name')}{aliases_str}")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"[ERROR] Failed to load configuration: {e}", file=sys.stderr)
        return 1


def handle_inspect(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser().resolve()
    if not path.exists():
        print(f"[ERROR] File not found: {path}", file=sys.stderr)
        return 1

    config = LibraryConfig.load(args.config)
    organizer = LibraryOrganizer(config)

    meta = read_audio_metadata(path)
    match = organizer.matcher.match(meta)

    print("=" * 60)
    print(f"  INSPECT AUDIO FILE: {path.name}")
    print("=" * 60)
    print(f"  File Path:         {path}")
    print(f"  Embedded Metadata: {'Yes' if meta.has_embedded_metadata else 'No (Using Filename)'}")
    print(f"  Metadata Source:   {meta.metadata_source}")
    print(f"  Artist Tag:        {meta.artist}")
    print(f"  Album Artist Tag:  {meta.album_artist}")
    print(f"  Title Tag:         {meta.title}")
    print(f"  Album Tag:         {meta.album}")
    print(f"  Track Number:      {meta.track_number}")
    print("-" * 60)
    print(f"  Match Status:      {'MATCHED' if match.matched else 'UNMATCHED / REVIEW'}")
    if match.matched:
        print(f"  Canonical Artist:  {match.canonical_artist}")
        print(f"  Category:          {match.category_key}")
        print(f"  Target Subfolder:  {match.target_subfolder}")
        print(f"  Confidence:        {match.confidence}")
    else:
        print(f"  Reason:            {match.reason}")
    print("=" * 60)
    return 0


def main() -> int:
    parser = build_parser()
    if len(sys.argv) == 1:
        args = parser.parse_args(["run", "--dry-run"])
    else:
        args = parser.parse_args()

    if args.command == "run":
        return handle_run(args)
    elif args.command == "inventory":
        return handle_inventory(args)
    elif args.command == "acquire":
        return handle_acquire(args)
    elif args.command == "watch":
        return handle_watch(args)
    elif args.command == "check-config":
        return handle_check_config(args)
    elif args.command == "inspect":
        return handle_inspect(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
