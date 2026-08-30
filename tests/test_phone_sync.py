import json
import pytest
from pathlib import Path
import subprocess
from unittest.mock import patch, MagicMock

from music_agent.cli import main
from music_agent.config import LibraryConfig
from music_agent.phone_sync import (
    PhoneSyncManager,
    DirectoryBackend,
    AdbBackend,
    SyncStatus,
    format_bytes,
)
from tests.make_dummy_audio import create_dummy_mp3


@pytest.fixture
def mock_sync_env(tmp_path):
    source_lib = tmp_path / "Songs"
    target_phone = tmp_path / "PhoneMusic"
    reports = tmp_path / "Reports"

    source_lib.mkdir(parents=True, exist_ok=True)
    target_phone.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)

    # Populate organized source library with Category/Artist hierarchy
    f1 = source_lib / "International" / "Billie Eilish" / "Billie Eilish - Ocean Eyes.mp3"
    f2 = source_lib / "Indian" / "Telugu" / "Sid Sriram" / "Sid Sriram - Samajavaragamana.mp3"
    f1.parent.mkdir(parents=True, exist_ok=True)
    f2.parent.mkdir(parents=True, exist_ok=True)

    create_dummy_mp3(f1, artist="Billie Eilish", title="Ocean Eyes")
    create_dummy_mp3(f2, artist="Sid Sriram", title="Samajavaragamana")

    config = LibraryConfig.load()
    config.destination_dir = source_lib

    return {
        "config": config,
        "source_lib": source_lib,
        "target_phone": target_phone,
        "reports": reports,
        "f1": f1,
        "f2": f2,
    }


def test_directory_backend_readiness_and_list(mock_sync_env):
    target = mock_sync_env["target_phone"]
    backend = DirectoryBackend(target_dir=target)

    ready, msg = backend.check_ready()
    assert ready is True
    assert "ready" in msg

    # Initially empty
    files = backend.list_target_files(str(target))
    assert len(files) == 0


def test_phone_sync_dry_run_discovers_and_transfers_nothing(mock_sync_env):
    config = mock_sync_env["config"]
    source = mock_sync_env["source_lib"]
    target = mock_sync_env["target_phone"]

    backend = DirectoryBackend(target_dir=target)
    manager = PhoneSyncManager(config=config, backend=backend, source_dir=source, target_base=str(target))

    report = manager.plan_sync()
    assert report.dry_run is True
    assert report.total_source_files == 2
    assert report.to_copy_count == 2
    assert report.already_exists_count == 0
    assert report.transferred_count == 0
    assert report.total_transfer_bytes > 0

    # Ensure zero files transferred to target
    target_files = list(target.rglob("*"))
    assert len(target_files) == 0


def test_phone_sync_live_execution_transfers_and_verifies(mock_sync_env):
    config = mock_sync_env["config"]
    source = mock_sync_env["source_lib"]
    target = mock_sync_env["target_phone"]

    backend = DirectoryBackend(target_dir=target)
    manager = PhoneSyncManager(config=config, backend=backend, source_dir=source, target_base=str(target))

    # 1. First sync -> Transfers all 2 files
    report = manager.execute_sync()
    assert report.dry_run is False
    assert report.transferred_count == 2
    assert report.error_count == 0

    # Verify files on target preserved hierarchy
    dest1 = target / "International" / "Billie Eilish" / "Billie Eilish - Ocean Eyes.mp3"
    dest2 = target / "Indian" / "Telugu" / "Sid Sriram" / "Sid Sriram - Samajavaragamana.mp3"
    assert dest1.exists()
    assert dest2.exists()

    # 2. Second sync -> Detects already existing and transfers 0
    report2 = manager.execute_sync()
    assert report2.to_copy_count == 0
    assert report2.already_exists_count == 2
    assert report2.transferred_count == 0


def test_phone_sync_preserves_existing_foreign_files_on_phone(mock_sync_env):
    config = mock_sync_env["config"]
    source = mock_sync_env["source_lib"]
    target = mock_sync_env["target_phone"]

    # Phone already has a user song that is NOT in the library
    phone_custom_song = target / "CustomRecording.mp3"
    phone_custom_song.write_bytes(b"EXISTING_USER_RECORDING_NEVER_DELETE")

    backend = DirectoryBackend(target_dir=target)
    manager = PhoneSyncManager(config=config, backend=backend, source_dir=source, target_base=str(target))

    report = manager.execute_sync()
    assert report.transferred_count == 2

    # The custom song on phone MUST NOT be deleted
    assert phone_custom_song.exists()
    assert phone_custom_song.read_bytes() == b"EXISTING_USER_RECORDING_NEVER_DELETE"


def test_adb_backend_device_detection_and_push():
    backend = AdbBackend()

    # Mock `adb devices` with authorized device
    mock_proc_devices = MagicMock()
    mock_proc_devices.returncode = 0
    mock_proc_devices.stdout = "List of devices attached\n1234567890ABC\tdevice\n"

    # Mock `adb shell find`
    mock_proc_find = MagicMock()
    mock_proc_find.returncode = 0
    mock_proc_find.stdout = "/sdcard/Music/International/Billie Eilish/Billie Eilish - Ocean Eyes.mp3\n"

    # Mock `adb shell mkdir` and `adb push`
    mock_proc_ok = MagicMock()
    mock_proc_ok.returncode = 0
    mock_proc_ok.stdout = ""

    # Mock `adb shell wc -c`
    mock_proc_wc = MagicMock()
    mock_proc_wc.returncode = 0
    mock_proc_wc.stdout = "1024\n"

    with patch("shutil.which", return_value="/opt/homebrew/bin/adb"):
        with patch.object(backend, "_run_adb_cmd") as mock_run:
            mock_run.side_effect = [
                mock_proc_devices,  # check_ready
                mock_proc_find,     # list_target_files
                mock_proc_ok,       # mkdir
                mock_proc_ok,       # push
                mock_proc_wc,       # verify wc -c
            ]

            ready, msg = backend.check_ready()
            assert ready is True
            assert backend.device_id == "1234567890ABC"

            files = backend.list_target_files("/sdcard/Music")
            assert "International/Billie Eilish/Billie Eilish - Ocean Eyes.mp3" in files

            success, transfer_msg = backend.transfer_file(
                Path("/tmp/song.mp3"), "International/Artist/Song.mp3", "/sdcard/Music"
            )
            assert success is True

            verified = backend.verify_transferred_file(
                "International/Artist/Song.mp3", expected_size=1024, expected_hash=None, target_base="/sdcard/Music"
            )
            assert verified is True


def test_adb_backend_unauthorized_device_reporting():
    backend = AdbBackend()

    mock_proc_devices = MagicMock()
    mock_proc_devices.returncode = 0
    mock_proc_devices.stdout = "List of devices attached\n1234567890ABC\tunauthorized\n"

    with patch("shutil.which", return_value="/opt/homebrew/bin/adb"):
        with patch.object(backend, "_run_adb_cmd", return_value=mock_proc_devices):
            ready, msg = backend.check_ready()
            assert ready is False
            assert "unauthorized" in msg.lower()


def test_phone_sync_report_and_manifest_generation(mock_sync_env):
    config = mock_sync_env["config"]
    source = mock_sync_env["source_lib"]
    target = mock_sync_env["target_phone"]
    reports_dir = mock_sync_env["reports"]

    backend = DirectoryBackend(target_dir=target)
    manager = PhoneSyncManager(config=config, backend=backend, source_dir=source, target_base=str(target))

    report = manager.execute_sync()
    md_file, csv_file = manager.generate_reports(report, output_dir=reports_dir)

    assert md_file.exists()
    assert csv_file.exists()

    md_content = md_file.read_text(encoding="utf-8")
    assert "# Music Library Agent - Phone Sync Report (Execution)" in md_content
    assert "Successfully Transferred" in md_content
    assert "Billie Eilish" in md_content

    csv_content = csv_file.read_text(encoding="utf-8")
    assert "Relative_Path,Status,Size_Bytes" in csv_content
    assert "Billie Eilish" in csv_content


def test_cli_sync_phone_dry_run_and_flag_collision(mock_sync_env, capsys):
    # Dry run preview
    with patch("sys.argv", [
        "music-agent", "sync-phone", "--dry-run",
        "--source", str(mock_sync_env["source_lib"]),
        "--target-dir", str(mock_sync_env["target_phone"]),
        "--backend", "directory",
        "--report-dir", str(mock_sync_env["reports"]),
    ]):
        ret = main()
        assert ret == 0
        captured = capsys.readouterr()
        assert "ANDROID PHONE MUSIC SYNC [DRY-RUN PREVIEW]" in captured.out
        assert "New Files to Copy:         2" in captured.out

    # Flag collision
    with patch("sys.argv", ["music-agent", "sync-phone", "--dry-run", "--execute"]):
        ret = main()
        assert ret == 1
        captured = capsys.readouterr()
        assert "Cannot specify both" in captured.err
