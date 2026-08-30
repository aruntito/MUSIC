import json
import pytest
from pathlib import Path
from unittest.mock import patch

from music_agent.acquisition import AcquisitionManager
from music_agent.cli import main
from music_agent.config import LibraryConfig
from music_agent.connectors.base import TrackCandidate, AcquisitionSourceStatus
from music_agent.connectors.official_stores import OfficialStoreConnector
from music_agent.inventory import WishlistTrack
from tests.make_dummy_audio import create_dummy_mp3


@pytest.fixture
def mock_acq_env(tmp_path):
    dest = tmp_path / "Songs"
    review = tmp_path / "Review"
    reports = tmp_path / "Reports"
    dest.mkdir(parents=True, exist_ok=True)
    review.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    config = LibraryConfig.load()
    config.destination_dir = dest
    config.review_dir = review

    wishlist_path = tmp_path / "test_wishlist.json"
    wishlist_data = {
        "version": 1,
        "tracks": [
            {
                "artist": "Billie Eilish",
                "title": "Ocean Eyes",
                "category": "International",
                "priority": "core",
                "status": "wanted"
            },
            {
                "artist": "Sid Sriram",
                "title": "Samajavaragamana",
                "category": "Indian/Telugu",
                "priority": "core",
                "status": "wanted"
            }
        ]
    }
    wishlist_path.write_text(json.dumps(wishlist_data), encoding="utf-8")

    return {
        "config": config,
        "wishlist_path": wishlist_path,
        "dest": dest,
        "review": review,
        "reports": reports,
    }


def test_acquisition_dry_run_discovers_and_never_downloads(mock_acq_env):
    config = mock_acq_env["config"]
    manager = AcquisitionManager(config, wishlist_path=mock_acq_env["wishlist_path"])

    report = manager.run_acquisition(dry_run=True)
    assert report.total_requested == 2
    assert report.dry_run is True
    assert report.purchase_required_count == 2
    assert report.acquired_count == 0

    dest_files = list(mock_acq_env["dest"].rglob("*"))
    assert len(dest_files) == 0


def test_commercial_tracks_marked_purchase_required(mock_acq_env):
    conn = OfficialStoreConnector()
    results = conn.search("Billie Eilish", "Ocean Eyes")
    assert len(results) >= 1
    for r in results:
        assert r.status == AcquisitionSourceStatus.PURCHASE_REQUIRED
        assert r.store_url is not None
        assert "https://music.apple.com" in r.store_url or "https://bandcamp.com" in r.store_url
        assert r.is_policy_approved is False
        assert conn.verify_policy_compliance(r) is False
        assert conn.stage_track(r, Path("/tmp")) is None


def test_authorized_local_candidate_can_be_staged_and_imported(mock_acq_env, tmp_path):
    config = mock_acq_env["config"]

    user_file = tmp_path / "Billie Eilish - Ocean Eyes.mp3"
    create_dummy_mp3(user_file, artist="Billie Eilish", title="Ocean Eyes")

    wishlist_path = tmp_path / "auth_wishlist.json"
    wishlist_data = {
        "version": 1,
        "tracks": [
            {
                "artist": "Billie Eilish",
                "title": "Ocean Eyes",
                "category": "International",
                "priority": "core",
                "status": "wanted",
                "source_url": str(user_file)
            }
        ]
    }
    wishlist_path.write_text(json.dumps(wishlist_data), encoding="utf-8")

    manager = AcquisitionManager(config, wishlist_path=wishlist_path)

    # Dry-Run should find AVAILABLE but not import
    report_dry = manager.run_acquisition(dry_run=True)
    assert report_dry.available_count == 1
    assert report_dry.acquired_count == 0
    assert len(list(mock_acq_env["dest"].rglob("*"))) == 0

    # Live acquisition should import and verify hash
    report_live = manager.run_acquisition(dry_run=False)
    assert report_live.acquired_count == 1

    target_file = mock_acq_env["dest"] / "International" / "Billie Eilish" / "Billie Eilish - Ocean Eyes.mp3"
    assert target_file.exists()

    assert user_file.exists()


def test_acquisition_reports_generation(mock_acq_env):
    config = mock_acq_env["config"]
    manager = AcquisitionManager(config, wishlist_path=mock_acq_env["wishlist_path"])

    report = manager.run_acquisition(dry_run=True)
    md_file, csv_file = manager.generate_reports(report, output_dir=mock_acq_env["reports"])

    assert md_file.exists()
    assert csv_file.exists()

    md_content = md_file.read_text(encoding="utf-8")
    assert "# Music Library Agent - Dry-Run Discovery Report" in md_content
    assert "PURCHASE_REQUIRED" in md_content
    assert "Billie Eilish" in md_content

    csv_content = csv_file.read_text(encoding="utf-8")
    assert "Artist,Title,Category,Status,Source" in csv_content
    assert "Billie Eilish,Ocean Eyes,International,PURCHASE_REQUIRED" in csv_content


def test_cli_acquire_dry_run_and_flag_collision(mock_acq_env, capsys):
    with patch("sys.argv", [
        "music-agent", "acquire", "--dry-run",
        "--wishlist", str(mock_acq_env["wishlist_path"]),
        "--dest", str(mock_acq_env["dest"]),
        "--report-dir", str(mock_acq_env["reports"]),
    ]):
        ret = main()
        assert ret == 0
        captured = capsys.readouterr()
        assert "MUSIC ACQUISITION DISCOVERY" in captured.out
        assert "Official Store Purchase Required: 2" in captured.out

    with patch("sys.argv", ["music-agent", "acquire", "--dry-run", "--execute"]):
        ret = main()
        assert ret == 1
        captured = capsys.readouterr()
        assert "Cannot specify both" in captured.err
