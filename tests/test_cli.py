import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from music_agent.cli import main
from tests.make_dummy_audio import create_dummy_mp3


def test_cli_check_config(capsys):
    with patch("sys.argv", ["music-agent", "check-config"]):
        ret = main()
        assert ret == 0
        captured = capsys.readouterr()
        assert "LIBRARY CONFIGURATION SUMMARY" in captured.out
        assert "Billie Eilish" in captured.out
        assert "Indian/Telugu" in captured.out
        assert "Indian/Hindi" in captured.out


def test_cli_inspect(tmp_path, capsys):
    f = tmp_path / "inspect_test.mp3"
    create_dummy_mp3(f, artist="Billie Eilish", title="Ocean Eyes")

    with patch("sys.argv", ["music-agent", "inspect", str(f)]):
        ret = main()
        assert ret == 0
        captured = capsys.readouterr()
        assert "INSPECT AUDIO FILE" in captured.out
        assert "Billie Eilish" in captured.out
        assert "MATCHED" in captured.out


def test_cli_run_dry_run_and_execute(tmp_path, capsys):
    inbox = tmp_path / "Inbox"
    dest = tmp_path / "Songs"
    review = tmp_path / "Review"
    reports = tmp_path / "Reports"

    inbox.mkdir(parents=True, exist_ok=True)
    f = inbox / "Billie Eilish - Ocean Eyes.mp3"
    create_dummy_mp3(f, artist="Billie Eilish", title="Ocean Eyes")

    # 1. Test CLI Dry-Run
    with patch("sys.argv", [
        "music-agent", "run", "--dry-run",
        "--source", str(inbox),
        "--dest", str(dest),
        "--review", str(review),
        "--report-dir", str(reports),
    ]):
        ret = main()
        assert ret == 0
        captured = capsys.readouterr()
        assert "DRY-RUN PREVIEW" in captured.out
        assert "Planned Imports:           1" in captured.out

    # 2. Test CLI Execute
    with patch("sys.argv", [
        "music-agent", "run", "--execute",
        "--source", str(inbox),
        "--dest", str(dest),
        "--review", str(review),
        "--report-dir", str(reports),
    ]):
        ret = main()
        assert ret == 0
        captured = capsys.readouterr()
        assert "LIVE IMPORT EXECUTED" in captured.out
        assert (dest / "International" / "Billie Eilish" / "Billie Eilish - Ocean Eyes.mp3").exists()


def test_cli_run_rejects_both_dry_run_and_execute(capsys):
    with patch("sys.argv", ["music-agent", "run", "--dry-run", "--execute"]):
        ret = main()
        assert ret == 1
        captured = capsys.readouterr()
        assert "Cannot specify both" in captured.err


def test_cli_watch_defaults_to_dry_run():
    with patch("sys.argv", ["music-agent", "watch"]):
        with patch("music_agent.watcher.FolderWatcher.run_loop") as mock_loop:
            ret = main()
            assert ret == 0
            # Ensure dry_run argument passed to run_loop is True
            mock_loop.assert_called_once_with(poll_interval=2.0, dry_run=True)


def test_cli_watch_execute_passes_live_mode():
    with patch("sys.argv", ["music-agent", "watch", "--execute"]):
        with patch("music_agent.watcher.FolderWatcher.run_loop") as mock_loop:
            ret = main()
            assert ret == 0
            # Ensure dry_run argument passed to run_loop is False
            mock_loop.assert_called_once_with(poll_interval=2.0, dry_run=False)


def test_cli_watch_rejects_both_dry_run_and_execute(capsys):
    with patch("sys.argv", ["music-agent", "watch", "--dry-run", "--execute"]):
        ret = main()
        assert ret == 1
        captured = capsys.readouterr()
        assert "Cannot specify both" in captured.err
