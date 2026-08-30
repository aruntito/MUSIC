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
from music_agent.phone_sync import PhoneSyncManager, DirectoryBackend, AdbBackend, format_bytes
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

    # Command: sync-phone
    sync_parser = subparsers.add_parser("sync-phone", help="Safely sync organized music from library to Android phone")
    sync_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview files to transfer without copying (Default behavior)",
    )
    sync_parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute live copy sync to phone",
    )
    sync_parser.add_argument(
        "--backend",
        choices=["auto", "adb", "directory"],
        default="auto",
        help="Transfer transport backend (default: auto)",
    )
    sync_parser.add_argument(
        "--target-dir",
        "-t",
        type=str,
        default=None,
        help="Target folder for directory sync (e.g. /Volumes/PhoneSD/Music)",
    )
    sync_parser.add_argument(
        "--device-dir",
        type=str,
        default="/sdcard/Music",
        help="Target music directory on Android phone (default: /sdcard/Music)",
    )
    sync_parser.add_argument(
        "--source",
        "-s",
        type=str,
        default=None,
        help="Override source library directory (default: ~/Downloads/Songs)",
    )
    sync_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to library_rules.json configuration file",
    )
    sync_parser.add_argument(
        "--report-dir",
        type=str,
        default="reports",
        help="Directory to save sync reports (default: ./reports)",
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
    inspect_parser.add_argument(
        "--enrich",
        action="store_true",
        default=False,
        help="Query MusicBrainz to enrich missing metadata (requires network)",
    )

    # Command: playlist
    pl_parser = subparsers.add_parser("playlist", help="Generate M3U8 playlists from organized library")
    pl_parser.add_argument(
        "--source",
        "-s",
        type=str,
        default=None,
        help="Library root directory (default: ~/Downloads/Songs)",
    )
    pl_parser.add_argument(
        "--playlist-dir",
        type=str,
        default="playlists",
        help="Output directory for .m3u8 files (default: ./playlists)",
    )

    # Command: stats
    stats_parser = subparsers.add_parser("stats", help="Show library statistics and health report")
    stats_parser.add_argument(
        "--source",
        "-s",
        type=str,
        default=None,
        help="Library root directory (default: ~/Downloads/Songs)",
    )
    stats_parser.add_argument(
        "--review-dir",
        type=str,
        default=None,
        help="Review queue directory (default: ~/Music/Review)",
    )
    stats_parser.add_argument(
        "--wishlist",
        "-w",
        type=str,
        default=None,
        help="Path to wishlist.json (default: config/wishlist.json)",
    )
    stats_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
    )

    # Command: full-sync
    fs_parser = subparsers.add_parser(
        "full-sync",
        help="One-command pipeline: organize → inventory → playlists → phone sync",
    )
    fs_parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview all steps without copying any files",
    )
    fs_parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Execute all steps (organize, inventory, playlists, phone sync)",
    )
    fs_parser.add_argument(
        "--enrich",
        action="store_true",
        default=False,
        help="Enable MusicBrainz metadata enrichment + artwork (requires network)",
    )
    fs_parser.add_argument(
        "--skip-organize",
        action="store_true",
        default=False,
        help="Skip the organize (run) step",
    )
    fs_parser.add_argument(
        "--skip-playlist",
        action="store_true",
        default=False,
        help="Skip playlist generation",
    )
    fs_parser.add_argument(
        "--skip-phone",
        action="store_true",
        default=False,
        help="Skip the phone sync step",
    )
    fs_parser.add_argument(
        "--config",
        "-c",
        type=str,
        default=None,
        help="Path to library_rules.json configuration file",
    )
    fs_parser.add_argument(
        "--playlist-dir",
        type=str,
        default="playlists",
        help="Output directory for generated playlists (default: ./playlists)",
    )
    fs_parser.add_argument(
        "--backend",
        choices=["auto", "adb", "directory"],
        default="auto",
        help="Phone sync transport backend (default: auto)",
    )
    fs_parser.add_argument(
        "--target-dir",
        "-t",
        type=str,
        default=None,
        help="Target folder for directory phone sync",
    )
    fs_parser.add_argument(
        "--device-dir",
        type=str,
        default="/sdcard/Music",
        help="Target directory on Android phone (default: /sdcard/Music)",
    )

    # Command: analyze
    analyze_parser = subparsers.add_parser("analyze", help="Analyze loudness / EBU R128 and write ReplayGain tags")
    analyze_parser.add_argument(
        "--path",
        "-p",
        type=str,
        default=None,
        help="Audio file or directory to analyze (default: ~/Downloads/Songs)",
    )
    analyze_parser.add_argument(
        "--write-tags",
        action="store_true",
        default=False,
        help="Explicitly write REPLAYGAIN_TRACK_GAIN and REPLAYGAIN_TRACK_PEAK tags (no re-encoding)",
    )

    # Command: dupes
    dupes_parser = subparsers.add_parser("dupes", help="Detect duplicate files using SHA-256 and optional AcoustID fingerprinting")
    dupes_parser.add_argument(
        "--path",
        "-p",
        type=str,
        default=None,
        help="Directory to scan for duplicates (default: ~/Downloads/Songs)",
    )
    dupes_parser.add_argument(
        "--no-acoustid",
        action="store_true",
        default=False,
        help="Disable acoustic fingerprinting check (use SHA-256 only)",
    )
    dupes_parser.add_argument(
        "--format",
        choices=["table", "json"],
        default="table",
        help="Output format (default: table)",
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
        print(f"  Policy-Approved Free Available:  {report.available_count}")
        print(f"  Official Store Purchase Options: {report.purchase_required_count}")
        print(f"  Stream Only (No DRM-free files): {report.stream_only_count}")
        print(f"  Unavailable / Unknown:           {report.unavailable_count}")
        if not dry_run:
            print(f"  Successfully Staged & Imported:  {report.acquired_count}")
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


def handle_sync_phone(args: argparse.Namespace) -> int:
    try:
        config = LibraryConfig.load(args.config)
        source_dir = Path(args.source).expanduser().resolve() if args.source else config.destination_dir

        if args.dry_run and args.execute:
            print("[ERROR] Cannot specify both '--dry-run' and '--execute'. Choose one.", file=sys.stderr)
            return 1

        dry_run = True
        if args.execute:
            dry_run = False
        else:
            if not args.dry_run:
                print("\n[INFO] No sync mode specified. Defaulting to DRY-RUN preview for safety.")
                print("       Run with '--execute' to perform actual transfer to phone.\n")
            dry_run = True

        # Choose transport backend
        backend = None
        target_location = args.device_dir

        if args.backend == "directory" or args.target_dir:
            target_path = Path(args.target_dir).expanduser().resolve() if args.target_dir else Path("/Volumes/Phone/Music")
            backend = DirectoryBackend(target_dir=target_path)
            target_location = str(target_path)
        elif args.backend == "adb":
            backend = AdbBackend()
            target_location = args.device_dir
        else:  # auto
            # Try ADB first
            adb_test = AdbBackend()
            ready, msg = adb_test.check_ready()
            if ready:
                backend = adb_test
                target_location = args.device_dir
            elif args.target_dir:
                backend = DirectoryBackend(target_dir=Path(args.target_dir).expanduser().resolve())
                target_location = str(args.target_dir)
            else:
                # Default to ADB reporting instructions or fallback to target dir
                backend = adb_test
                target_location = args.device_dir

        sync_mgr = PhoneSyncManager(
            config=config,
            backend=backend,
            source_dir=source_dir,
            target_base=target_location,
        )

        print("=" * 65)
        print(f"  ANDROID PHONE MUSIC SYNC [{'DRY-RUN PREVIEW' if dry_run else 'LIVE SAFE COPY'}]")
        print("=" * 65)
        print(f"  Source Library:     {source_dir}")
        print(f"  Transport Backend:  {backend.name}")
        print(f"  Target Destination: {target_location}")
        print("Analyzing library and phone status...")

        report = sync_mgr.plan_sync() if dry_run else sync_mgr.execute_sync()
        md_file, csv_file = sync_mgr.generate_reports(report, output_dir=Path(args.report_dir))

        print("\n" + "=" * 65)
        print("  PHONE SYNC SUMMARY")
        print("=" * 65)
        print(f"  Total Source Tracks:       {report.total_source_files}")
        print(f"  New Files to Copy:         {report.to_copy_count}")
        print(f"  Already Present on Phone:  {report.already_exists_count}")
        print(f"  Total Transfer Payload:    {format_bytes(report.total_transfer_bytes)}")
        if not dry_run:
            print(f"  Successfully Transferred:  {report.transferred_count}")
        if report.error_count > 0:
            print(f"  Errors / Failed:           {report.error_count}")
        print("=" * 65)
        print(f"  [✓] Sync Report:   {md_file}")
        print(f"  [✓] Sync Manifest: {csv_file}")
        print("=" * 65)

        if dry_run and report.to_copy_count > 0:
            print("\nTo transfer files to your phone, run:")
            print("  python3 music_agent_cli.py sync-phone --execute")

        return 0 if report.error_count == 0 else 1
    except Exception as e:
        print(f"[ERROR] Phone sync failed: {e}", file=sys.stderr)
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
    print(f"  Year Tag:          {meta.year or '—'}")
    print(f"  Genre Tag:         {meta.genre or '—'}")
    print(f"  Track Number:      {meta.track_number}")

    # Optional MusicBrainz enrichment
    if getattr(args, "enrich", False):
        from music_agent.enricher import MusicBrainzEnricher  # noqa: PLC0415
        print("-" * 60)
        print("  [Enriching via MusicBrainz — requires network]")
        enricher = MusicBrainzEnricher()
        result = enricher.lookup(meta.artist or "", meta.title or "")
        if result:
            print(f"  MB Artist:         {result.artist}")
            print(f"  MB Title:          {result.title}")
            print(f"  MB Album:          {result.album or '—'}")
            print(f"  MB Year:           {result.year or '—'}")
            print(f"  MB Genre:          {result.genre or '—'}")
            print(f"  MB Recording ID:   {result.mbid_recording or '—'}")
            print(f"  MB Confidence:     {result.confidence:.0%}")
        else:
            print("  MB Result:         No match found")

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


def handle_playlist(args: argparse.Namespace) -> int:
    """Generate M3U8 playlists from the organized library."""
    from music_agent.playlist import generate_playlists  # noqa: PLC0415

    library_root = Path(args.source).expanduser().resolve() if args.source else None
    playlist_dir = Path(args.playlist_dir).resolve()

    print("=" * 60)
    print("  PLAYLIST GENERATOR")
    print("=" * 60)
    print(f"  Library Root:   {library_root or '~/Downloads/Songs (default)'}")
    print(f"  Playlist Dir:   {playlist_dir}")
    print("Scanning library and generating playlists...")

    report = generate_playlists(library_root=library_root, playlist_dir=playlist_dir)

    print(f"\n  Tracks scanned:    {report.total_tracks_scanned}")
    print(f"  Playlists created: {len(report.generated)}")
    for pl in report.generated:
        print(f"    ✅  {pl.name}.m3u8  ({pl.entry_count} tracks)")
    print("=" * 60)
    return 0


def handle_stats(args: argparse.Namespace) -> int:
    """Show library statistics and health report."""
    from music_agent.library_stats import scan_library, format_stats_table  # noqa: PLC0415

    library_root = Path(args.source).expanduser().resolve() if args.source else None
    review_dir = Path(args.review_dir).expanduser().resolve() if args.review_dir else None
    wishlist_path = Path(args.wishlist).expanduser().resolve() if args.wishlist else None

    stats = scan_library(
        library_root=library_root,
        review_dir=review_dir,
        wishlist_path=wishlist_path,
    )

    if args.format == "json":
        import json  # noqa: PLC0415
        data = {
            "library_root": str(stats.library_root),
            "scanned_at": stats.scanned_at,
            "total_tracks": stats.total_tracks,
            "total_bytes": stats.total_bytes,
            "by_category": stats.by_category,
            "by_format": stats.by_format,
            "by_artist": {k: v.track_count for k, v in stats.by_artist.items()},
            "tracks_missing_tags": len(stats.tracks_missing_tags),
            "wishlist_total": stats.wishlist_total,
            "wishlist_present": stats.wishlist_present,
            "review_count": stats.review_count,
        }
        print(json.dumps(data, indent=2))
    else:
        print(format_stats_table(stats))

    return 0


def handle_full_sync(args: argparse.Namespace) -> int:
    """
    One-command pipeline: organize → inventory → playlists → phone sync.
    MusicBrainz enrichment + artwork only when --enrich is passed explicitly.
    """
    if args.dry_run and args.execute:
        print("[ERROR] Cannot specify both '--dry-run' and '--execute'.", file=sys.stderr)
        return 1

    dry_run = not args.execute
    mode_label = "DRY-RUN PREVIEW" if dry_run else "LIVE EXECUTION"

    print("=" * 60)
    print(f"  FULL SYNC PIPELINE  [{mode_label}]")
    print("=" * 60)

    step = 0
    rc = 0

    # ── Step 1: Organize ────────────────────────────────────────────
    if not args.skip_organize:
        step += 1
        print(f"\n[{step}] Organize (run {'--dry-run' if dry_run else '--execute'})")
        run_args = argparse.Namespace(
            command="run",
            dry_run=dry_run,
            execute=not dry_run,
            config=args.config,
            source=None,
            dest=None,
            review=None,
            report_dir="reports",
            no_report=False,
        )
        rc = handle_run(run_args)
        if rc != 0:
            print(f"[!] Organize step returned exit code {rc} — stopping.", file=sys.stderr)
            return rc
    else:
        print("\n[skip] Organize step skipped (--skip-organize)")

    # ── Step 2: Inventory ───────────────────────────────────────────
    step += 1
    print(f"\n[{step}] Inventory")
    inv_args = argparse.Namespace(
        command="inventory",
        config=args.config,
        wishlist=None,
        dest=None,
        report_dir="reports",
    )
    handle_inventory(inv_args)

    # ── Step 3: MusicBrainz Enrichment (only if --enrich) ──────────
    if args.enrich:
        step += 1
        print(f"\n[{step}] MusicBrainz Enrichment (--enrich enabled)")
        print("       Network requests will be made to MusicBrainz API.")
        print("       Rate-limited to 1 request/second. This may take a while.")
        # Enrichment is applied per-track when individual files are inspected
        # with --enrich; at the full-sync level we just notify.
        print("       Tip: Use 'music-agent inspect <file> --enrich' per track for now.")
    else:
        print("\n[offline] Enrichment skipped (pass --enrich to enable MusicBrainz lookup)")

    # ── Step 4: Playlists ───────────────────────────────────────────
    if not args.skip_playlist:
        step += 1
        print(f"\n[{step}] Generate Playlists")
        pl_args = argparse.Namespace(
            command="playlist",
            source=None,
            playlist_dir=args.playlist_dir,
        )
        handle_playlist(pl_args)
    else:
        print("\n[skip] Playlist step skipped (--skip-playlist)")

    # ── Step 5: Phone Sync ──────────────────────────────────────────
    if not args.skip_phone:
        step += 1
        print(f"\n[{step}] Phone Sync ({'DRY-RUN' if dry_run else 'LIVE'})")
        sync_args = argparse.Namespace(
            command="sync-phone",
            dry_run=dry_run,
            execute=not dry_run,
            backend=args.backend,
            target_dir=args.target_dir,
            device_dir=args.device_dir,
            source=None,
            config=args.config,
            report_dir="reports",
        )
        handle_sync_phone(sync_args)
    else:
        print("\n[skip] Phone sync step skipped (--skip-phone)")

    print("\n" + "=" * 60)
    print(f"  FULL SYNC COMPLETE  [{mode_label}]")
    print("=" * 60)
    return 0


def handle_analyze(args: argparse.Namespace) -> int:
    """Analyze loudness / EBU R128 and optionally write ReplayGain tags."""
    from music_agent.loudness import analyze_loudness, analyze_directory, write_replaygain_tags  # noqa: PLC0415

    target_path = Path(args.path).expanduser().resolve() if args.path else Path.home() / "Downloads" / "Songs"

    if not target_path.exists():
        print(f"[ERROR] Target path does not exist: {target_path}", file=sys.stderr)
        return 1

    print("=" * 60)
    print("  LOUDNESS & REPLAYGAIN ANALYSIS")
    print("=" * 60)
    print(f"  Target:     {target_path}")
    print(f"  Write Tags: {'Yes (ReplayGain tags)' if args.write_tags else 'No (Analysis only)'}")
    print("-" * 60)

    if target_path.is_file():
        info = analyze_loudness(target_path)
        if not info:
            print(f"[ERROR] Failed to analyze {target_path.name} (ensure ffmpeg is available).", file=sys.stderr)
            return 1
        print(f"  File:               {info.file_path.name}")
        print(f"  Integrated LUFS:    {info.integrated_lufs:.2f} LUFS")
        print(f"  True Peak:          {info.true_peak_dbfs:.2f} dBTP")
        print(f"  Loudness Range:     {info.lra_lu:.2f} LU")
        print(f"  ReplayGain Gain:    {info.replaygain_gain_db:+.2f} dB")
        print(f"  ReplayGain Peak:    {info.replaygain_peak:.6f}")
        if args.write_tags:
            success = write_replaygain_tags(target_path, info)
            print(f"  Tags Written:       {'✅ Success' if success else '❌ Failed'}")
    else:
        results = analyze_directory(target_path, write_tags=args.write_tags)
        print(f"  Analyzed {len(results)} audio file(s):")
        for info in results:
            tag_status = " [tags written]" if args.write_tags else ""
            print(f"    {info.file_path.name:<40} {info.integrated_lufs:>6.2f} LUFS  {info.replaygain_gain_db:>+6.2f} dB{tag_status}")

    print("=" * 60)
    return 0


def handle_dupes(args: argparse.Namespace) -> int:
    """Detect duplicates using SHA-256 and optional AcoustID fingerprinting."""
    from music_agent.fingerprint import find_duplicates  # noqa: PLC0415

    scan_path = Path(args.path).expanduser().resolve() if args.path else Path.home() / "Downloads" / "Songs"

    if not scan_path.exists():
        print(f"[ERROR] Directory does not exist: {scan_path}", file=sys.stderr)
        return 1

    use_acoustid = not args.no_acoustid
    groups = find_duplicates(scan_path, use_acoustid=use_acoustid)

    if args.format == "json":
        import json  # noqa: PLC0415
        out = [
            {
                "canonical": str(g.canonical_path),
                "duplicates": [str(d) for d in g.duplicates],
                "method": g.method,
                "confidence": g.confidence,
                "note": g.note,
            }
            for g in groups
        ]
        print(json.dumps(out, indent=2))
        return 0

    print("=" * 60)
    print("  DUPLICATE FILE DETECTION (ADVISORY ONLY)")
    print("=" * 60)
    print(f"  Scan Directory: {scan_path}")
    print(f"  AcoustID:       {'Enabled (if fpcalc present)' if use_acoustid else 'Disabled'}")
    print(f"  Duplicate Groups Found: {len(groups)}")
    print("-" * 60)

    if not groups:
        print("  ✅ No duplicate files found.")
    else:
        for i, g in enumerate(groups, 1):
            print(f"\n  [Group {i}] Method: {g.method.upper()} ({g.confidence}) — {g.note}")
            print(f"    ⭐ Primary:   {g.canonical_path.name}")
            for d in g.duplicates:
                print(f"    ⚠ Duplicate: {d.name} ({d.parent.name})")

    print("\n" + "=" * 60)
    print("  Note: No files were deleted or modified. This report is advisory.")
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
    elif args.command == "sync-phone":
        return handle_sync_phone(args)
    elif args.command == "check-config":
        return handle_check_config(args)
    elif args.command == "inspect":
        return handle_inspect(args)
    elif args.command == "playlist":
        return handle_playlist(args)
    elif args.command == "stats":
        return handle_stats(args)
    elif args.command == "full-sync":
        return handle_full_sync(args)
    elif args.command == "analyze":
        return handle_analyze(args)
    elif args.command == "dupes":
        return handle_dupes(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
