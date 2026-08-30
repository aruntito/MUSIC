"""
Tests for M3U8 playlist generation.
"""

import tempfile
from pathlib import Path

import pytest

from music_agent.playlist import generate_playlists, MIN_TRACKS_FOR_ARTIST_PLAYLIST
from tests.make_dummy_audio import create_dummy_mp3


def _build_library(tmp_path: Path) -> Path:
    """
    Build a minimal fake organized library structure.

    International/
      Billie Eilish/
        Billie Eilish - Ocean Eyes.mp3
        Billie Eilish - Bad Guy.mp3
      Linkin Park/
        Linkin Park - Numb.mp3
    Indian/
      Telugu/
        Anirudh Ravichander/
          Anirudh Ravichander - Hukum.mp3
    """
    lib = tmp_path / "Songs"

    be_dir = lib / "International" / "Billie Eilish"
    be_dir.mkdir(parents=True)
    create_dummy_mp3(be_dir / "Billie Eilish - Ocean Eyes.mp3")
    create_dummy_mp3(be_dir / "Billie Eilish - Bad Guy.mp3")

    lp_dir = lib / "International" / "Linkin Park"
    lp_dir.mkdir(parents=True)
    create_dummy_mp3(lp_dir / "Linkin Park - Numb.mp3")

    ind_dir = lib / "Indian" / "Telugu" / "Anirudh Ravichander"
    ind_dir.mkdir(parents=True)
    create_dummy_mp3(ind_dir / "Anirudh Ravichander - Hukum.mp3")

    return lib


class TestPlaylistGenerator:

    def test_generates_all_tracks_playlist(self, tmp_path):
        lib = _build_library(tmp_path)
        pdir = tmp_path / "playlists"
        report = generate_playlists(library_root=lib, playlist_dir=pdir)

        all_tracks = pdir / "All Tracks.m3u8"
        assert all_tracks.exists(), "All Tracks.m3u8 should be generated"
        content = all_tracks.read_text()
        assert "#EXTM3U" in content
        assert report.total_tracks_scanned == 4

    def test_generates_category_playlists(self, tmp_path):
        lib = _build_library(tmp_path)
        pdir = tmp_path / "playlists"
        generate_playlists(library_root=lib, playlist_dir=pdir)

        assert (pdir / "International.m3u8").exists()
        # Indian category with sub-category "Telugu" maps to "Indian"
        found = any(p.name.startswith("Indian") for p in pdir.glob("*.m3u8"))
        assert found, "Indian category playlist should be generated"

    def test_generates_artist_playlist_above_threshold(self, tmp_path):
        lib = _build_library(tmp_path)
        pdir = tmp_path / "playlists"
        generate_playlists(library_root=lib, playlist_dir=pdir)

        # Billie Eilish has 2 tracks ≥ MIN_TRACKS threshold
        billie_playlist = pdir / "Artists" / "Billie Eilish.m3u8"
        assert billie_playlist.exists(), "Billie Eilish should get an artist playlist"

    def test_no_artist_playlist_below_threshold(self, tmp_path):
        lib = _build_library(tmp_path)
        pdir = tmp_path / "playlists"
        generate_playlists(library_root=lib, playlist_dir=pdir)

        # Linkin Park has 1 track < MIN_TRACKS threshold
        lp_playlist = pdir / "Artists" / "Linkin Park.m3u8"
        assert not lp_playlist.exists(), "Linkin Park should NOT get an artist playlist (only 1 track)"

    def test_m3u8_uses_relative_paths(self, tmp_path):
        lib = _build_library(tmp_path)
        pdir = tmp_path / "playlists"
        generate_playlists(library_root=lib, playlist_dir=pdir)

        content = (pdir / "All Tracks.m3u8").read_text()
        # Should use relative paths, not absolute
        assert str(lib) not in content, "Playlist should not contain absolute paths"
        assert "../Songs/" in content

    def test_empty_library_returns_empty_report(self, tmp_path):
        empty_lib = tmp_path / "EmptySongs"
        empty_lib.mkdir()
        pdir = tmp_path / "playlists"
        report = generate_playlists(library_root=empty_lib, playlist_dir=pdir)

        assert report.total_tracks_scanned == 0
        assert len(report.generated) == 0

    def test_nonexistent_library_returns_empty_report(self, tmp_path):
        pdir = tmp_path / "playlists"
        report = generate_playlists(
            library_root=tmp_path / "DoesNotExist",
            playlist_dir=pdir,
        )
        assert report.total_tracks_scanned == 0
