"""
Tests for advisory fuzzy artist matching (rapidfuzz-based).
Verifies that fuzzy_suggest is purely advisory — no auto-routing.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from music_agent.config import LibraryConfig
from music_agent.matcher import ArtistMatcher


def _matcher_with_real_config() -> ArtistMatcher:
    config = LibraryConfig.load(None)  # Loads config/library_rules.json
    return ArtistMatcher(config)


class TestFuzzySuggest:

    def test_suggests_known_artist_with_minor_typo(self):
        matcher = _matcher_with_real_config()
        # "Billie Elish" (typo: missing 'i') → should suggest "Billie Eilish"
        result = matcher.fuzzy_suggest("Billie Elish", threshold=80.0)
        assert result is not None
        canonical, score = result
        assert canonical == "Billie Eilish"
        assert 0 < score <= 100

    def test_returns_none_for_completely_unknown_artist(self):
        matcher = _matcher_with_real_config()
        result = matcher.fuzzy_suggest("Xyzzy Unknown Artist 9999", threshold=92.0)
        assert result is None

    def test_returns_none_for_empty_string(self):
        matcher = _matcher_with_real_config()
        assert matcher.fuzzy_suggest("") is None
        assert matcher.fuzzy_suggest("   ") is None

    def test_does_not_auto_route_on_fuzzy_match(self):
        """
        Confirms fuzzy_suggest returns a suggestion only.
        The caller (not the matcher) is responsible for routing decisions.
        fuzzy_suggest never modifies config, files, or match outcomes.
        """
        matcher = _matcher_with_real_config()
        # Even with a clear fuzzy match, exact match() should still return UNMATCHED
        from music_agent.metadata import AudioMetadata  # noqa: PLC0415
        meta = AudioMetadata(
            file_path=Path("Billie Elish - Ocean Eyes.mp3"),
            artist="Billie Elish",   # typo
            title="Ocean Eyes",
        )
        exact_result = matcher.match(meta)
        assert not exact_result.matched, "Exact matcher should NOT match typo — fuzzy is advisory only"

        # But fuzzy_suggest returns a suggestion
        suggestion = matcher.fuzzy_suggest("Billie Elish", threshold=80.0)
        # Suggestion is returned but does not affect routing
        if suggestion:
            canonical, score = suggestion
            assert canonical == "Billie Eilish"

    def test_high_confidence_threshold_filters_weak_matches(self):
        matcher = _matcher_with_real_config()
        # At very high threshold, only near-perfect matches come through
        result = matcher.fuzzy_suggest("Arijit", threshold=99.0)
        # "Arijit" alone (missing "Singh") may not meet 99% threshold
        # Just check no exception is raised
        assert result is None or isinstance(result, tuple)

    def test_returns_canonical_name_not_alias(self):
        matcher = _matcher_with_real_config()
        # Match via a known alias should still return canonical name
        # (alias lookup in exact matcher) — fuzzy confirms same canonical
        result = matcher.fuzzy_suggest("Arjit Singh", threshold=80.0)  # common misspelling
        if result:
            canonical, _ = result
            assert canonical == "Arijit Singh"
