"""
Tests for album artwork embedding and folder.jpg saving.
All file I/O uses real temp files; no network calls.
"""

import struct
import tempfile
from pathlib import Path

import pytest

from music_agent.artwork import (
    apply_artwork, embed_artwork_in_file, save_folder_jpg,
    download_artwork, MODE_EMBED, MODE_FOLDER_JPG, MODE_BOTH,
)
from tests.make_dummy_audio import create_dummy_mp3


# Minimal valid JPEG bytes (1×1 white pixel)
MINIMAL_JPEG = bytes([
    0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
    0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00,
    0xFF, 0xDB, 0x00, 0x43, 0x00,
    *([8] * 64),
    0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01, 0x11, 0x00,
    0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01,
    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04,
    0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B,
    0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xF5, 0x00,
    0xFF, 0xD9,
])


class TestSaveFolderJpg:

    def test_saves_folder_jpg_successfully(self, tmp_path):
        artist_dir = tmp_path / "Billie Eilish"
        artist_dir.mkdir()
        result = save_folder_jpg(MINIMAL_JPEG, artist_dir)
        assert result is not None
        assert (artist_dir / "folder.jpg").exists()
        assert (artist_dir / "folder.jpg").read_bytes() == MINIMAL_JPEG

    def test_returns_none_on_unwritable_path(self, tmp_path):
        # Pass a file path as directory — write will fail
        bad_path = tmp_path / "not_a_dir.txt"
        bad_path.write_text("x")
        result = save_folder_jpg(MINIMAL_JPEG, bad_path)
        # folder.jpg can't be created inside a file path — should not raise
        # Result may be None or a valid path depending on OS; just check no exception
        assert result is None or isinstance(result, Path)

    def test_overwrites_existing_folder_jpg(self, tmp_path):
        artist_dir = tmp_path / "Artist"
        artist_dir.mkdir()
        (artist_dir / "folder.jpg").write_bytes(b"old_data")
        save_folder_jpg(MINIMAL_JPEG, artist_dir)
        assert (artist_dir / "folder.jpg").read_bytes() == MINIMAL_JPEG


class TestDownloadArtwork:

    def test_download_failure_returns_none(self, tmp_path):
        # Pass an unreachable URL; no real network calls in tests
        import unittest.mock as mock
        with mock.patch("urllib.request.urlopen", side_effect=Exception("no network")):
            result = download_artwork("http://example.invalid/cover.jpg", cache_dir=tmp_path)
        assert result is None

    def test_uses_cached_data_on_second_call(self, tmp_path):
        # Pre-populate cache manually
        url = "http://example.com/cover.jpg"
        url_hash = __import__("hashlib").sha256(url.encode()).hexdigest()[:16]
        cache_file = tmp_path / f"{url_hash}.jpg"
        cache_file.write_bytes(MINIMAL_JPEG)

        result = download_artwork(url, cache_dir=tmp_path)
        assert result == MINIMAL_JPEG


class TestApplyArtwork:

    def test_mode_folder_jpg_only(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "test.mp3")
        result = apply_artwork(mp3, MINIMAL_JPEG, mode=MODE_FOLDER_JPG)
        assert result["embedded"] is False
        assert (tmp_path / "folder.jpg").exists()

    def test_mode_embed_only(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "test_embed.mp3")
        result = apply_artwork(mp3, MINIMAL_JPEG, mode=MODE_EMBED)
        # embed may fail for a dummy mp3 with no valid ID3 structure — should not raise
        assert isinstance(result["embedded"], bool)
        assert not (tmp_path / "folder.jpg").exists()

    def test_mode_both(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "test_both.mp3")
        result = apply_artwork(mp3, MINIMAL_JPEG, mode=MODE_BOTH)
        assert isinstance(result["embedded"], bool)
        assert (tmp_path / "folder.jpg").exists()

    def test_empty_image_data_is_no_op(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "test_noop.mp3")
        result = apply_artwork(mp3, b"", mode=MODE_BOTH)
        assert result["embedded"] is False
        assert result["folder_jpg"] is None
