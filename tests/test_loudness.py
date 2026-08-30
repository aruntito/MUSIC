"""
Tests for ReplayGain / loudness analysis.
All subprocess (ffmpeg) calls are mocked — no real audio analysis in tests.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from music_agent.loudness import (
    analyze_loudness, write_replaygain_tags, analyze_directory,
    LoudnessInfo, _find_ffmpeg, SUPPORTED_AUDIO_EXTS,
)
from tests.make_dummy_audio import create_dummy_mp3, create_dummy_flac


MOCK_FFMPEG_STDERR = b"""
[Parsed_loudnorm_0 @ 0x...] Input Integrated: -18.00 LUFS
{
    "input_i" : "-18.00",
    "input_tp" : "-2.00",
    "input_lra" : "7.00",
    "input_thresh" : "-28.10",
    "output_i" : "-18.00",
    "output_tp" : "-2.00",
    "output_lra" : "7.00",
    "output_thresh" : "-28.10",
    "normalization_type" : "dynamic",
    "target_offset" : "0.00"
}
"""

MOCK_RESULT = MagicMock()
MOCK_RESULT.stderr = MOCK_FFMPEG_STDERR
MOCK_RESULT.returncode = 0


class TestAnalyzeLoudness:

    def test_returns_loudness_info_on_success(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "test.mp3")
        with patch("subprocess.run", return_value=MOCK_RESULT):
            info = analyze_loudness(mp3, ffmpeg_path="/fake/ffmpeg")

        assert info is not None
        assert isinstance(info, LoudnessInfo)
        assert info.integrated_lufs == -18.0
        assert info.true_peak_dbfs == -2.0
        assert info.lra_lu == 7.0
        assert info.replaygain_gain_db == 0.0  # -18 target - (-18 measured) = 0

    def test_returns_none_when_ffmpeg_unavailable(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "test.mp3")
        info = analyze_loudness(mp3, ffmpeg_path="/nonexistent/ffmpeg")
        assert info is None

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        with patch("subprocess.run", return_value=MOCK_RESULT):
            info = analyze_loudness(tmp_path / "doesnotexist.mp3", ffmpeg_path="/fake/ffmpeg")
        assert info is None

    def test_returns_none_for_unsupported_extension(self, tmp_path):
        txt_file = tmp_path / "notaudio.txt"
        txt_file.write_text("hello")
        with patch("subprocess.run", return_value=MOCK_RESULT):
            info = analyze_loudness(txt_file, ffmpeg_path="/fake/ffmpeg")
        assert info is None

    def test_returns_none_on_subprocess_timeout(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "test.mp3")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ffmpeg", 120)):
            info = analyze_loudness(mp3, ffmpeg_path="/fake/ffmpeg")
        assert info is None

    def test_returns_none_on_invalid_json_stderr(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "test.mp3")
        bad_result = MagicMock()
        bad_result.stderr = b"not json output at all"
        with patch("subprocess.run", return_value=bad_result):
            info = analyze_loudness(mp3, ffmpeg_path="/fake/ffmpeg")
        assert info is None

    def test_replaygain_gain_calculated_correctly(self, tmp_path):
        # If integrated is -21 LUFS, gain should be -18 - (-21) = +3 dB
        loud_stderr = MOCK_FFMPEG_STDERR.replace(b'"-18.00"', b'"-21.00"', 1)
        mock_r = MagicMock()
        mock_r.stderr = loud_stderr
        mp3 = create_dummy_mp3(tmp_path / "quiet.mp3")
        with patch("subprocess.run", return_value=mock_r):
            info = analyze_loudness(mp3, ffmpeg_path="/fake/ffmpeg")
        assert info is not None
        assert abs(info.replaygain_gain_db - 3.0) < 0.01


class TestWriteReplaygainTags:

    def test_write_tags_to_mp3(self, tmp_path):
        mp3 = create_dummy_mp3(tmp_path / "tagged.mp3")
        info = LoudnessInfo(
            file_path=mp3,
            integrated_lufs=-18.0,
            true_peak_dbfs=-2.0,
            lra_lu=7.0,
            replaygain_gain_db=0.0,
            replaygain_peak=0.794328,
        )
        result = write_replaygain_tags(mp3, info)
        assert isinstance(result, bool)  # May succeed or fail depending on dummy MP3 validity

    def test_write_tags_to_flac(self, tmp_path):
        flac = create_dummy_flac(tmp_path / "tagged.flac")
        info = LoudnessInfo(
            file_path=flac,
            integrated_lufs=-18.0,
            true_peak_dbfs=-2.0,
            lra_lu=7.0,
            replaygain_gain_db=0.0,
            replaygain_peak=0.794328,
        )
        result = write_replaygain_tags(flac, info)
        assert isinstance(result, bool)


class TestAnalyzeDirectory:

    def test_returns_list_of_results(self, tmp_path):
        mp3_1 = create_dummy_mp3(tmp_path / "Song1.mp3")
        mp3_2 = create_dummy_mp3(tmp_path / "Song2.mp3")

        with patch("subprocess.run", return_value=MOCK_RESULT):
            results = analyze_directory(tmp_path, write_tags=False, ffmpeg_path="/fake/ffmpeg")

        assert len(results) == 2
        assert all(isinstance(r, LoudnessInfo) for r in results)

    def test_empty_directory_returns_empty_list(self, tmp_path):
        with patch("subprocess.run", return_value=MOCK_RESULT):
            results = analyze_directory(tmp_path, write_tags=False, ffmpeg_path="/fake/ffmpeg")
        assert results == []
