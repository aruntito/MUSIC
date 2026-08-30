"""
Reporter module for formatting console summaries and generating detailed Markdown reports.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional
from music_agent.organizer import PipelineReport, ActionType


def format_console_summary(report: PipelineReport) -> str:
    """Format an ANSI-colored / clean terminal summary report."""
    mode_str = "[DRY-RUN PREVIEW (No files modified)]" if report.dry_run else "[LIVE IMPORT EXECUTED]"
    import_label = "Planned Imports:           " if report.dry_run else "Imported / Approved:       "
    dup_label =    "Duplicates (To Skip):      " if report.dry_run else "Duplicates (Skipped):      "
    unmatch_label ="Unmatched (To Review):     " if report.dry_run else "Unmatched (Routed Review): "
    sep = "=" * 70

    lines = [
        "",
        sep,
        f"  MUSIC LIBRARY AGENT - INGESTION REPORT {mode_str}",
        sep,
        f"  Total Files Scanned:       {report.total_scanned}",
        f"  {import_label}{report.imported_count}",
        f"  {dup_label}{report.duplicate_count}",
        f"  {unmatch_label}{report.unmatched_count}",
        f"  Missing Embedded Metadata: {report.missing_metadata_count}",
        f"  Errors:                    {report.error_count}",
        f"  Duration:                  {report.duration_seconds:.2f}s",
        sep,
        "",
        "Action Details:",
    ]

    if not report.actions:
        lines.append("  (No audio files found in Inbox)")
    else:
        for idx, act in enumerate(report.actions, start=1):
            if report.dry_run:
                icon = {
                    ActionType.IMPORT: "✓ [PLAN: IMPORT]",
                    ActionType.DUPLICATE: "= [PLAN: SKIP DUP]",
                    ActionType.REVIEW: "? [PLAN: REVIEW]",
                    ActionType.MISSING_METADATA: "⚠ [PLAN: NO-META]",
                    ActionType.ERROR: "✗ [ERROR]",
                }.get(act.action_type, "[INFO]")
            else:
                icon = {
                    ActionType.IMPORT: "✓ [IMPORTED]",
                    ActionType.DUPLICATE: "= [DUPLICATE]",
                    ActionType.REVIEW: "? [REVIEW]",
                    ActionType.MISSING_METADATA: "⚠ [NO-META]",
                    ActionType.ERROR: "✗ [ERROR]",
                }.get(act.action_type, "[INFO]")

            lines.append(f"  {idx:3d}. {icon:18s} {act.source_path.name}")
            lines.append(f"       Status: {act.message}")
            if act.target_path:
                lines.append(f"       Target: {act.target_path}")
            if act.error_detail:
                lines.append(f"       Error:  {act.error_detail}")

    lines.append(sep)
    return "\n".join(lines)


def generate_markdown_report(report: PipelineReport, output_dir: Optional[Path] = None) -> Path:
    """Generate a comprehensive timestamped Markdown report document."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode_title = "Dry-Run Preview" if report.dry_run else "Import Run"
    import_col_name = "Planned Imports" if report.dry_run else "Imported / Approved"
    import_col_desc = "Tracks identified for approved import" if report.dry_run else "Matched and copied to approved artist destination"

    if output_dir is None:
        output_dir = Path.cwd() / "reports"
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    report_file = output_dir / f"import_report_{timestamp}.md"

    md_lines = [
        f"# Music Library Agent - {mode_title} Report",
        "",
        f"- **Date & Time**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Mode**: `{'Dry-Run (Simulated Preview)' if report.dry_run else 'Live Import (Copy-Only)'}`",
        f"- **Processing Time**: {report.duration_seconds:.3f} seconds",
        "",
        "## Summary Statistics",
        "",
        "| Metric | Count | Description |",
        "| :--- | :---: | :--- |",
        f"| **Total Files Scanned** | **{report.total_scanned}** | Total audio files detected in Inbox |",
        f"| **{import_col_name}** | **{report.imported_count}** | {import_col_desc} |",
        f"| **Duplicates Skipped** | **{report.duplicate_count}** | Identified identical SHA-256 hash or destination file |",
        f"| **Unmatched / Review** | **{report.unmatched_count}** | Routed safely to Review directory |",
        f"| **Missing Metadata** | **{report.missing_metadata_count}** | Embedded ID3/tag missing (fallback used) |",
        f"| **Errors** | **{report.error_count}** | Failures or corrupt files |",
        "",
        "## Processed Files Detail",
        "",
        "| # | Source File | Action | Matched Category | Target Path | Notes |",
        "| :---: | :--- | :---: | :--- | :--- | :--- |",
    ]

    for idx, act in enumerate(report.actions, start=1):
        src_name = act.source_path.name
        action_name = act.action_type.value
        cat = act.match_result.category_key if (act.match_result and act.match_result.matched) else "None / Review"
        target = str(act.target_path) if act.target_path else "None"
        notes = act.message
        if act.error_detail:
            notes += f" (Error: {act.error_detail})"

        # Escape pipe symbols for markdown table
        src_safe = src_name.replace("|", "\\|")
        notes_safe = notes.replace("|", "\\|")
        target_safe = target.replace("|", "\\|")

        md_lines.append(f"| {idx} | `{src_safe}` | `{action_name}` | {cat} | `{target_safe}` | {notes_safe} |")

    md_lines.extend([
        "",
        "## Safety & Integrity Notice",
        "- Original files in the source inbox remain completely untouched.",
        "- Audio files were verified by SHA-256 hash.",
        "- No audio transcoding was performed.",
        ""
    ])

    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    return report_file
