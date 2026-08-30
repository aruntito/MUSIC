"""
Tests for library statistics and health reporting.
"""

import json
import tempfile
from pathlib import Path

import pytest

from music_agent.library_stats import scan_library, format_stats_table, _human_size
from tests.make_dummy_audio import create_dummy_mp3


def _build_library(tmp_path: Path) -> Path:
    lib = tmp_path / "Songs"

    be_dir = lib / "International" / "Billie Eilish"
    be_dir.mkdir(parents=True)
    create_dummy_mp3(be_dir / "Billie Eilish - Ocean Eyes.mp3")
    create_dummy_mp3(be_dir / "Billie Eilish - Bad Guy.mp3")

    lp_dir = lib / "International" / "Linkin Park"
    lp_dir.mkdir(parents=True)
    create_dummy_mp3(lp_dir / "Linkin Park - Numb.mp3")

    ind_dir = lib / "Indian" / "Arijit Singh"
    ind_dir.mkdir(parents=True)
    create_dummy_mp3(ind_dir / "Arijit Singh - Kesariya.mp3")

    return lib


def _build_wishlist(tmp_path: Path, tracks: list) -> Path:
    wl = tmp_path / "wishlist.json"
    wl.write_text(json.dumps({"version": 1, "tracks": tracks}), encoding="utf-8")
    return wl


class TestScanLibrary:

    def test_counts_tracks_and_size(self, tmp_path):
        lib = _build_library(tmp_path)
        stats = scan_library(library_root=lib, review_dir=tmp_path / "Review")

        assert stats.total_tracks == 4
        assert stats.total_bytes > 0

    def test_category_breakdown(self, tmp_path):
        lib = _build_library(tmp_path)
        stats = scan_library(library_root=lib, review_dir=tmp_path / "Review")

        assert "International" in stats.by_category
        assert stats.by_category["International"] == 3
        assert "Indian" in stats.by_category
        assert stats.by_category["Indian"] == 1

    def test_format_breakdown(self, tmp_path):
        lib = _build_library(tmp_path)
        stats = scan_library(library_root=lib, review_dir=tmp_path / "Review")

        assert "mp3" in stats.by_format
        assert stats.by_format["mp3"] == 4

    def test_artist_breakdown(self, tmp_path):
        lib = _build_library(tmp_path)
        stats = scan_library(library_root=lib, review_dir=tmp_path / "Review")

        assert "Billie Eilish" in stats.by_artist
        assert stats.by_artist["Billie Eilish"].track_count == 2
        assert "Linkin Park" in stats.by_artist
        assert stats.by_artist["Linkin Park"].track_count == 1

    def test_review_queue_counted(self, tmp_path):
        lib = _build_library(tmp_path)
        review = tmp_path / "Review"
        review.mkdir()
        create_dummy_mp3(review / "Unknown - SomeSong.mp3")
        stats = scan_library(library_root=lib, review_dir=review)

        assert stats.review_count == 1
        assert stats.review_bytes > 0

    def test_wishlist_coverage(self, tmp_path):
        lib = _build_library(tmp_path)
        # Wishlist: 2 tracks in library, 1 missing
        wl = _build_wishlist(tmp_path, [
            {"artist": "Billie Eilish", "title": "Ocean Eyes"},
            {"artist": "Billie Eilish", "title": "Bad Guy"},
            {"artist": "Linkin Park", "title": "In the End"},   # NOT in library
        ])
        stats = scan_library(library_root=lib, review_dir=tmp_path / "Review", wishlist_path=wl)

        assert stats.wishlist_total == 3
        assert stats.wishlist_present == 2

    def test_empty_library(self, tmp_path):
        lib = tmp_path / "Songs"
        lib.mkdir()
        stats = scan_library(library_root=lib, review_dir=tmp_path / "Review")

        assert stats.total_tracks == 0
        assert stats.total_bytes == 0

    def test_nonexistent_library(self, tmp_path):
        stats = scan_library(
            library_root=tmp_path / "DoesNotExist",
            review_dir=tmp_path / "Review",
        )
        assert stats.total_tracks == 0


class TestFormatStatsTable:

    def test_format_stats_table_is_string(self, tmp_path):
        lib = _build_library(tmp_path)
        stats = scan_library(library_root=lib, review_dir=tmp_path / "Review")
        output = format_stats_table(stats)

        assert isinstance(output, str)
        assert "MUSIC LIBRARY STATISTICS" in output
        assert "International" in output
        assert "mp3" in output


class TestHumanSize:
    def test_bytes(self):
        assert "B" in _human_size(512)

    def test_kilobytes(self):
        assert "KB" in _human_size(2048)

    def test_megabytes(self):
        assert "MB" in _human_size(5 * 1024 * 1024)
