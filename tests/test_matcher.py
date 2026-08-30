import pytest
from pathlib import Path
from music_agent.config import LibraryConfig
from music_agent.matcher import ArtistMatcher
from music_agent.metadata import AudioMetadata


@pytest.fixture
def config():
    return LibraryConfig.load()


@pytest.fixture
def matcher(config):
    return ArtistMatcher(config)


def test_exact_artist_match(matcher):
    meta = AudioMetadata(
        file_path=Path("dummy.mp3"),
        artist="Billie Eilish",
        title="Ocean Eyes"
    )
    result = matcher.match(meta)
    assert result.matched is True
    assert result.canonical_artist == "Billie Eilish"
    assert result.target_subfolder == "International/Billie Eilish"
    assert result.confidence == "exact"


def test_alias_match(matcher):
    meta = AudioMetadata(
        file_path=Path("dummy.mp3"),
        artist="SPB",
        title="Priyathama"
    )
    result = matcher.match(meta)
    assert result.matched is True
    assert result.canonical_artist == "S. P. Balasubrahmanyam"
    assert result.target_subfolder == "Indian/Telugu"


def test_telugu_artist_match(matcher):
    meta = AudioMetadata(
        file_path=Path("dummy.mp3"),
        artist="Sid Sriram",
        title="Samajavaragamana"
    )
    result = matcher.match(meta)
    assert result.matched is True
    assert result.canonical_artist == "Sid Sriram"
    assert result.target_subfolder == "Indian/Telugu"


def test_hindi_artist_match(matcher):
    meta = AudioMetadata(
        file_path=Path("dummy.mp3"),
        artist="Arijit Singh",
        title="Kesariya"
    )
    result = matcher.match(meta)
    assert result.matched is True
    assert result.canonical_artist == "Arijit Singh"
    assert result.target_subfolder == "Indian/Hindi"


def test_featuring_primary_artist_match(matcher):
    meta = AudioMetadata(
        file_path=Path("dummy.mp3"),
        artist="Wiz Khalifa feat. Charlie Puth",
        title="See You Again"
    )
    result = matcher.match(meta)
    assert result.matched is True
    assert result.canonical_artist == "Wiz Khalifa"
    assert result.target_subfolder == "International/Wiz Khalifa"


def test_unrecognized_artist_routed_to_review(matcher):
    meta = AudioMetadata(
        file_path=Path("dummy.mp3"),
        artist="Random Unknown Local Band 123",
        title="Some Song"
    )
    result = matcher.match(meta)
    assert result.matched is False
    assert "not in approved library rules" in result.reason
