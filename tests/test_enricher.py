"""
Tests for MusicBrainzEnricher — all network I/O mocked.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from music_agent.enricher import MusicBrainzEnricher, EnrichedTrackInfo


def _make_mb_response(score=95, title="Ocean Eyes", artist="Billie Eilish",
                       album="Don't Smile at Me", year="2016", genre="Indie Pop",
                       recording_id="rec-mbid-001", release_id="rel-mbid-001"):
    return {
        "recordings": [{
            "id": recording_id,
            "score": score,
            "title": title,
            "artist-credit": [{"name": artist}],
            "releases": [{"id": release_id, "title": album, "date": year}],
            "tags": [{"name": genre, "count": 5}],
        }]
    }


class TestMusicBrainzEnricher:

    def _enricher(self, tmp_path):
        cache = tmp_path / "mb_cache.json"
        return MusicBrainzEnricher(cache_path=cache)

    def test_lookup_returns_enriched_info_on_successful_response(self, tmp_path):
        enricher = self._enricher(tmp_path)
        mb_data = _make_mb_response()

        with patch.object(enricher, "_get", return_value=mb_data):
            result = enricher.lookup("Billie Eilish", "Ocean Eyes")

        assert result is not None
        assert isinstance(result, EnrichedTrackInfo)
        assert result.artist == "Billie Eilish"
        assert result.title == "Ocean Eyes"
        assert result.album == "Don't Smile at Me"
        assert result.year == "2016"
        assert result.genre == "Indie Pop"
        assert result.mbid_recording == "rec-mbid-001"
        assert result.mbid_release == "rel-mbid-001"
        assert result.confidence == 0.95

    def test_lookup_uses_cache_on_second_call(self, tmp_path):
        enricher = self._enricher(tmp_path)
        mb_data = _make_mb_response()

        with patch.object(enricher, "_get", return_value=mb_data) as mock_get:
            enricher.lookup("Billie Eilish", "Ocean Eyes")
            enricher.lookup("Billie Eilish", "Ocean Eyes")

        # _get should only be called once — second call hits cache
        assert mock_get.call_count == 1

    def test_lookup_caches_negative_result(self, tmp_path):
        enricher = self._enricher(tmp_path)
        empty_response = {"recordings": []}

        with patch.object(enricher, "_get", return_value=empty_response) as mock_get:
            r1 = enricher.lookup("Unknown Artist", "Unknown Track")
            r2 = enricher.lookup("Unknown Artist", "Unknown Track")

        assert r1 is None
        assert r2 is None
        assert mock_get.call_count == 1  # negative cache hit on second call

    def test_lookup_returns_none_on_network_failure(self, tmp_path):
        enricher = self._enricher(tmp_path)

        with patch.object(enricher, "_get", return_value=None):
            result = enricher.lookup("Artist", "Song")

        assert result is None

    def test_cache_persists_across_instances(self, tmp_path):
        cache_path = tmp_path / "mb_cache.json"
        mb_data = _make_mb_response()

        e1 = MusicBrainzEnricher(cache_path=cache_path)
        with patch.object(e1, "_get", return_value=mb_data):
            e1.lookup("Billie Eilish", "Ocean Eyes")

        # Create a new enricher pointing at the same cache
        e2 = MusicBrainzEnricher(cache_path=cache_path)
        with patch.object(e2, "_get") as mock_get:
            result = e2.lookup("Billie Eilish", "Ocean Eyes")

        # Should read from cache without hitting network
        mock_get.assert_not_called()
        assert result is not None
        assert result.artist == "Billie Eilish"

    def test_lookup_missing_artist_or_title_returns_none(self, tmp_path):
        enricher = self._enricher(tmp_path)
        assert enricher.lookup("", "Ocean Eyes") is None
        assert enricher.lookup("Billie Eilish", "") is None
        assert enricher.lookup("", "") is None

    def test_year_normalised_to_4_digits(self, tmp_path):
        enricher = self._enricher(tmp_path)
        mb_data = _make_mb_response(year="2016-03-18")  # full date → should parse to "2016"

        with patch.object(enricher, "_get", return_value=mb_data):
            result = enricher.lookup("Billie Eilish", "Ocean Eyes")

        assert result is not None
        assert result.year == "2016"

    def test_get_artwork_url_returns_none_on_failure(self, tmp_path):
        enricher = self._enricher(tmp_path)

        with patch("requests.head", side_effect=Exception("network error")):
            url = enricher.get_artwork_url("some-mbid")

        assert url is None
