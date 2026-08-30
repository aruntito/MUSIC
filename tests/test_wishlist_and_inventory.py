import json
import pytest
from pathlib import Path
from music_agent.config import LibraryConfig
from music_agent.inventory import WishlistManager, WishlistTrack
from tests.make_dummy_audio import create_dummy_mp3


@pytest.fixture
def config():
    return LibraryConfig.load()


def test_wishlist_loads_and_all_artists_belong_to_44(config):
    manager = WishlistManager(config)
    tracks = manager.load_and_validate()
    assert len(tracks) > 0
    # Every track's artist must be in the approved list
    for t in tracks:
        assert t.artist in [rule.canonical_name for rule in config.artists.values()]


def test_wishlist_detects_unapproved_artist(config, tmp_path):
    bad_wishlist = tmp_path / "bad_wishlist.json"
    bad_wishlist.write_text(json.dumps({
        "version": 1,
        "tracks": [
            {
                "artist": "Unapproved Band 999",
                "title": "Song",
                "category": "International",
                "priority": "core",
                "status": "wanted"
            }
        ]
    }))

    manager = WishlistManager(config, wishlist_path=bad_wishlist)
    with pytest.raises(ValueError, match="is not in approved 44 artists"):
        manager.load_and_validate()


def test_wishlist_detects_duplicate_entries(config, tmp_path):
    dup_wishlist = tmp_path / "dup_wishlist.json"
    dup_wishlist.write_text(json.dumps({
        "version": 1,
        "tracks": [
            {
                "artist": "Billie Eilish",
                "title": "Ocean Eyes",
                "category": "International"
            },
            {
                "artist": "Billie Eilish",
                "title": "ocean eyes",
                "category": "International"
            }
        ]
    }))

    manager = WishlistManager(config, wishlist_path=dup_wishlist)
    with pytest.raises(ValueError, match="Duplicate entry in wishlist"):
        manager.load_and_validate()


def test_inventory_scan_and_report_generation(config, tmp_path):
    dest_dir = tmp_path / "Songs"
    reports_dir = tmp_path / "Reports"
    dest_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Place 1 track from wishlist in destination
    billie_dir = dest_dir / "International" / "Billie Eilish"
    billie_dir.mkdir(parents=True, exist_ok=True)
    f_billie = billie_dir / "Billie Eilish - Ocean Eyes.mp3"
    create_dummy_mp3(f_billie, artist="Billie Eilish", title="Ocean Eyes")

    # Place 1 unknown local file
    f_unknown = dest_dir / "Random - Unknown.mp3"
    create_dummy_mp3(f_unknown, artist="Random", title="Unknown")

    manager = WishlistManager(config)
    report = manager.scan_inventory(destination_dir=dest_dir)

    assert report.total_requested > 0
    assert report.found_locally_count == 1
    assert report.missing_count == report.total_requested - 1
    assert report.unknown_local_count == 1

    # Generate reports
    json_path, csv_path, md_path = manager.generate_reports(report, output_dir=reports_dir)
    assert json_path.exists()
    assert csv_path.exists()
    assert md_path.exists()

    # Check CSV content
    csv_content = csv_path.read_text(encoding="utf-8")
    assert "Artist,Title,Category,Priority,Status" in csv_content
    assert "Billie Eilish,Ocean Eyes" not in csv_content  # Ocean Eyes is found, so not missing
    assert "XXXTentacion,Moonlight" in csv_content       # Moonlight is missing
