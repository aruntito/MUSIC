import io
import pytest
from pathlib import Path
import zipfile
from music_agent.config import LibraryConfig
from music_agent.watcher import FolderWatcher, extract_audio_from_zip, is_safe_zip_member
from tests.make_dummy_audio import create_dummy_mp3, create_dummy_flac


@pytest.fixture
def config(tmp_path):
    cfg = LibraryConfig.load()
    cfg.source_dir = tmp_path / "Inbox"
    cfg.destination_dir = tmp_path / "Songs"
    cfg.review_dir = tmp_path / "Review"
    cfg.source_dir.mkdir(parents=True, exist_ok=True)
    cfg.destination_dir.mkdir(parents=True, exist_ok=True)
    cfg.review_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def test_zip_safe_path_checks(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()

    # Normal relative path
    zinfo_valid = zipfile.ZipInfo("song.mp3")
    assert is_safe_zip_member(staging, zinfo_valid) is True

    # Absolute path (/etc/passwd)
    zinfo_abs = zipfile.ZipInfo("/etc/passwd")
    assert is_safe_zip_member(staging, zinfo_abs) is False

    # Path traversal (../../evil.mp3)
    zinfo_trav = zipfile.ZipInfo("../../evil.mp3")
    assert is_safe_zip_member(staging, zinfo_trav) is False

    # Symlink entry
    zinfo_symlink = zipfile.ZipInfo("link_to_secret")
    zinfo_symlink.external_attr = 0o120777 << 16  # S_IFLNK
    assert is_safe_zip_member(staging, zinfo_symlink) is False


def test_zip_extraction_security_and_non_recursive(tmp_path):
    zip_path = tmp_path / "album.zip"
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    # Create dummy audio bytes
    mp3_tmp = tmp_path / "temp.mp3"
    create_dummy_mp3(mp3_tmp, artist="Billie Eilish", title="Ocean Eyes")
    mp3_bytes = mp3_tmp.read_bytes()

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("01. Billie Eilish - Ocean Eyes.mp3", mp3_bytes)
        zf.writestr("album_artwork.jpg", b"fake image bytes")
        zf.writestr("notes.txt", b"album notes")
        # Malicious traversal attempt
        zf.writestr("../../../evil.mp3", mp3_bytes)
        # Absolute path attempt
        zf.writestr("/tmp/malicious.mp3", mp3_bytes)
        # Nested zip (must be ignored, not extracted)
        zf.writestr("nested_bonus.zip", b"fake zip bytes")

    extracted = extract_audio_from_zip(zip_path, staging_dir, {".mp3", ".flac", ".m4a"})
    assert len(extracted) == 1
    assert extracted[0].name == "01. Billie Eilish - Ocean Eyes.mp3"
    assert not (tmp_path / "evil.mp3").exists()
    assert not (staging_dir / "nested_bonus.zip").exists()


def test_zip_duplicate_member_names_safe_handling(tmp_path):
    zip_path = tmp_path / "duplicates.zip"
    staging_dir = tmp_path / "staging"
    staging_dir.mkdir()

    mp3_tmp = tmp_path / "temp.mp3"
    create_dummy_mp3(mp3_tmp, artist="Billie Eilish", title="Ocean Eyes")
    mp3_bytes = mp3_tmp.read_bytes()

    with zipfile.ZipFile(zip_path, "w") as zf:
        # Two members with identical filenames in different zip subdirectories
        zf.writestr("disc1/track.mp3", mp3_bytes)
        zf.writestr("disc2/track.mp3", mp3_bytes)

    extracted = extract_audio_from_zip(zip_path, staging_dir, {".mp3"})
    assert len(extracted) == 2
    # Second track was saved with unique suffix, no overwriting
    assert extracted[0].name == "track.mp3"
    assert extracted[1].name == "track_1.mp3"


def test_watcher_detects_supported_and_ignores_unsupported(config, tmp_path):
    inbox = config.source_dir
    watcher = FolderWatcher(config, watch_dirs=[inbox])

    f_audio = inbox / "Billie Eilish - Bad Guy.mp3"
    create_dummy_mp3(f_audio, artist="Billie Eilish", title="Bad Guy")

    f_txt = inbox / "notes.txt"
    f_txt.write_text("hello")

    new_items = watcher.scan_new_items()
    assert f_audio in new_items
    assert f_txt not in new_items


def test_watcher_dry_run_modifies_nothing(config, tmp_path):
    inbox = config.source_dir
    watcher = FolderWatcher(config, watch_dirs=[inbox])

    f_audio = inbox / "Billie Eilish - Ocean Eyes.mp3"
    create_dummy_mp3(f_audio, artist="Billie Eilish", title="Ocean Eyes")

    event = watcher.process_item(f_audio, dry_run=True)
    assert len(event.actions) == 1
    assert event.actions[0].action_type.value == "IMPORT"
    assert event.actions[0].executed is False

    # Destination should have zero files
    dest_files = list(config.destination_dir.rglob("*"))
    assert len(dest_files) == 0

    # Source inbox file must remain untouched
    assert f_audio.exists()


def test_watcher_live_mode_executes_and_verifies_hash(config, tmp_path):
    inbox = config.source_dir
    watcher = FolderWatcher(config, watch_dirs=[inbox])

    f_audio = inbox / "Billie Eilish - Ocean Eyes.mp3"
    create_dummy_mp3(f_audio, artist="Billie Eilish", title="Ocean Eyes")

    event = watcher.process_item(f_audio, dry_run=False)
    assert len(event.actions) == 1
    action = event.actions[0]
    assert action.action_type.value == "IMPORT"
    assert action.executed is True

    # Destination file exists and SHA-256 matches
    dest_file = config.destination_dir / "International" / "Billie Eilish" / "Billie Eilish - Ocean Eyes.mp3"
    assert dest_file.exists()

    # Original inbox file must remain completely intact
    assert f_audio.exists()


def test_watcher_zip_integration_uses_organizer_pipeline(config, tmp_path):
    inbox = config.source_dir
    zip_file = inbox / "album.zip"

    mp3_tmp = tmp_path / "temp.mp3"
    create_dummy_mp3(mp3_tmp, artist="Billie Eilish", title="Ocean Eyes")
    mp3_bytes = mp3_tmp.read_bytes()

    with zipfile.ZipFile(zip_file, "w") as zf:
        zf.writestr("Billie Eilish - Ocean Eyes.mp3", mp3_bytes)

    watcher = FolderWatcher(config, watch_dirs=[inbox])
    event = watcher.process_item(zip_file, dry_run=False)

    assert event.is_zip is True
    assert len(event.actions) == 1
    assert event.actions[0].action_type.value == "IMPORT"
    assert event.actions[0].executed is True

    # Target file in destination
    dest_file = config.destination_dir / "International" / "Billie Eilish" / "Billie Eilish - Ocean Eyes.mp3"
    assert dest_file.exists()

    # Original zip file is preserved intact
    assert zip_file.exists()
