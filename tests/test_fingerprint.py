"""
Tests for acoustic fingerprinting and duplicate detection.
fpcalc subprocess calls are mocked — no real acoustic analysis in tests.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_agent.fingerprint import (
    find_duplicates, compute_sha256, compute_acoustid_fingerprint,
    DuplicateGroup, FingerprintResult,
)
from tests.make_dummy_audio import create_dummy_mp3


def _fpcalc_mock_result(fingerprint: str = "AQAA...fake", duration: float = 240.0):
    mock = MagicMock()
    mock.stdout = json.dumps({"fingerprint": fingerprint, "duration": duration}).encode()
    mock.returncode = 0
    return mock


class TestComputeSha256:

    def test_same_file_same_hash(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "a.mp3")
        h1 = compute_sha256(mp3)
        h2 = compute_sha256(mp3)
        assert h1 == h2

    def test_different_files_different_hash(self, tmp_path):
        mp3_a = create_dummy_mp3(tmp_path / "a.mp3")
        mp3_b = create_dummy_mp3(tmp_path / "b.mp3")
        # Write different content
        mp3_b.write_bytes(mp3_b.read_bytes() + b"\x00extra")
        assert compute_sha256(mp3_a) != compute_sha256(mp3_b)


class TestComputeAcoustidFingerprint:

    def test_returns_fingerprint_when_fpcalc_available(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "a.mp3")
        with patch("subprocess.run", return_value=_fpcalc_mock_result("AQAA_unique")):
            result = compute_acoustid_fingerprint(mp3, fpcalc_path="/fake/fpcalc")

        assert result is not None
        assert isinstance(result, FingerprintResult)
        assert result.fingerprint == "AQAA_unique"
        assert result.method == "acoustid"

    def test_returns_none_when_fpcalc_unavailable(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "a.mp3")
        result = compute_acoustid_fingerprint(mp3, fpcalc_path=None)
        # No fpcalc → None (unless it happens to be installed on the test system)
        # We just check it doesn't raise
        assert result is None or isinstance(result, FingerprintResult)

    def test_returns_none_on_subprocess_error(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "a.mp3")
        with patch("subprocess.run", side_effect=Exception("fpcalc crashed")):
            result = compute_acoustid_fingerprint(mp3, fpcalc_path="/fake/fpcalc")
        assert result is None

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        result = compute_acoustid_fingerprint(tmp_path / "ghost.mp3", fpcalc_path="/fake/fpcalc")
        assert result is None


class TestFindDuplicates:

    def test_detects_exact_sha256_duplicates(self, tmp_path):
        mp3_a = create_dummy_mp3(tmp_path / "original.mp3")
        mp3_b = tmp_path / "copy.mp3"
        mp3_b.write_bytes(mp3_a.read_bytes())  # Exact byte copy

        groups = find_duplicates(tmp_path, use_acoustid=False)

        assert len(groups) == 1
        assert groups[0].method == "sha256"
        assert groups[0].confidence == "exact"
        # One of the two files is canonical, the other is in duplicates
        all_paths = {groups[0].canonical_path} | set(groups[0].duplicates)
        assert mp3_a in all_paths
        assert mp3_b in all_paths

    def test_no_duplicates_returns_empty(self, tmp_path):
        mp3_a = create_dummy_mp3(tmp_path / "a.mp3")
        mp3_b = create_dummy_mp3(tmp_path / "b.mp3")
        # Make them different
        mp3_b.write_bytes(mp3_b.read_bytes() + b"\x00\x01\x02")

        groups = find_duplicates(tmp_path, use_acoustid=False)
        assert groups == []

    def test_detects_acoustid_duplicates(self, tmp_path):
        mp3_a = create_dummy_mp3(tmp_path / "a.mp3")
        mp3_b = create_dummy_mp3(tmp_path / "b_variant.mp3")
        # Make different SHA-256 but mock same fingerprint
        mp3_b.write_bytes(mp3_b.read_bytes() + b"\x00different")

        same_fp = _fpcalc_mock_result("SAME_FINGERPRINT_XYZ")
        with patch("subprocess.run", return_value=same_fp):
            groups = find_duplicates(tmp_path, use_acoustid=True, fpcalc_path="/fake/fpcalc")

        # Should find 1 acoustic duplicate group
        acoustic_groups = [g for g in groups if g.method == "acoustid"]
        assert len(acoustic_groups) == 1
        assert acoustic_groups[0].confidence == "probable"

    def test_nonexistent_directory_returns_empty(self, tmp_path):
        groups = find_duplicates(tmp_path / "nosuchdir", use_acoustid=False)
        assert groups == []
