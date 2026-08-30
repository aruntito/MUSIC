import pytest
from pathlib import Path
from music_agent.config import LibraryConfig
from music_agent.organizer import LibraryOrganizer, ActionType
from music_agent.reporter import generate_markdown_report
from tests.make_dummy_audio import create_dummy_mp3, create_dummy_flac, create_dummy_wav


@pytest.fixture
def mock_env(tmp_path):
    inbox = tmp_path / "Inbox"
    dest = tmp_path / "Songs"
    review = tmp_path / "Review"
    reports = tmp_path / "Reports"

    inbox.mkdir(parents=True, exist_ok=True)
    dest.mkdir(parents=True, exist_ok=True)
    review.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    # 1. Billie Eilish with embedded tags
    f1 = inbox / "track1.mp3"
    create_dummy_mp3(f1, artist="Billie Eilish", title="Ocean Eyes")

    # 2. Sid Sriram (Telugu) without embedded tags, fallback filename
    f2 = inbox / "Sid Sriram - Samajavaragamana.mp3"
    create_dummy_mp3(f2)  # No tags

    # 3. Anirudh (Telugu) FLAC with tags
    f3 = inbox / "hukum_track.flac"
    create_dummy_flac(f3, artist="Anirudh Ravichander", title="Hukum")

    # 4. Unknown artist -> Review
    f4 = inbox / "UnknownBand - Secret Track.wav"
    create_dummy_wav(f4, artist="UnknownBand", title="Secret Track")

    # 5. Duplicate of track1 in Inbox
    f5 = inbox / "track1_duplicate_copy.mp3"
    create_dummy_mp3(f5, artist="Billie Eilish", title="Ocean Eyes")

    config = LibraryConfig.load()
    config.source_dir = inbox
    config.destination_dir = dest
    config.review_dir = review

    return {
        "inbox": inbox,
        "dest": dest,
        "review": review,
        "reports": reports,
        "config": config,
        "files": [f1, f2, f3, f4, f5]
    }


def test_dry_run_does_not_modify_filesystem(mock_env):
    config = mock_env["config"]
    organizer = LibraryOrganizer(config)

    report = organizer.process(dry_run=True)
    assert report.total_scanned == 5
    assert report.imported_count == 3
    assert report.duplicate_count == 1
    assert report.unmatched_count == 1
    assert report.error_count == 0

    # Ensure zero files created in destination or review
    dest_files = list(mock_env["dest"].rglob("*"))
    review_files = list(mock_env["review"].rglob("*"))
    assert len(dest_files) == 0
    assert len(review_files) == 0

    # Ensure all original files in Inbox remain intact
    for f in mock_env["files"]:
        assert f.exists()


def test_live_copy_and_idempotency(mock_env):
    config = mock_env["config"]
    organizer = LibraryOrganizer(config)

    # First Live Run
    report = organizer.process(dry_run=False)
    assert report.total_scanned == 5
    assert report.imported_count == 3
    assert report.duplicate_count == 1
    assert report.unmatched_count == 1
    assert report.error_count == 0

    # Verify destination files
    billie_file = mock_env["dest"] / "International" / "Billie Eilish" / "Billie Eilish - Ocean Eyes.mp3"
    assert billie_file.exists()

    telugu_file1 = mock_env["dest"] / "Indian" / "Telugu" / "Sid Sriram - Samajavaragamana.mp3"
    assert telugu_file1.exists()

    telugu_file2 = mock_env["dest"] / "Indian" / "Telugu" / "Anirudh Ravichander - Hukum.flac"
    assert telugu_file2.exists()

    review_file = mock_env["review"] / "UnknownBand - Secret Track.wav"
    assert review_file.exists()

    # Verify original Inbox files are NEVER deleted or moved
    for f in mock_env["files"]:
        assert f.exists()

    # Second Run (Idempotency test)
    # Re-run organizer on same inbox: all files should be recognized as duplicates
    organizer2 = LibraryOrganizer(config)
    report2 = organizer2.process(dry_run=False)

    assert report2.total_scanned == 5
    assert report2.imported_count == 0
    assert report2.duplicate_count == 5
    assert report2.unmatched_count == 0
    assert report2.error_count == 0


def test_markdown_report_generation(mock_env):
    config = mock_env["config"]
    organizer = LibraryOrganizer(config)
    report = organizer.process(dry_run=True)

    report_path = generate_markdown_report(report, mock_env["reports"])
    assert report_path.exists()
    
    content = report_path.read_text(encoding="utf-8")
    assert "# Music Library Agent" in content
    assert "Planned Imports" in content
    assert "Billie Eilish" in content
    assert "Summary Statistics" in content
