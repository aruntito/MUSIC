import pytest
from pathlib import Path
from music_agent.config import LibraryConfig
from music_agent.matcher import ArtistMatcher
from music_agent.metadata import AudioMetadata

EXPECTED_INTERNATIONAL_ARTISTS = [
    "Billie Eilish",
    "XXXTentacion",
    "Wiz Khalifa",
    "Snoop Dogg",
    "The Weeknd",
    "Travis Scott",
    "Kanye West",
    "Kendrick Lamar",
    "Drake",
    "Juice WRLD",
    "Post Malone",
    "Arctic Monkeys",
    "Frank Ocean",
    "Tyler, The Creator",
    "Mac Miller",
    "Eminem",
    "21 Savage",
    "Metro Boomin",
    "Future",
    "Bruno Mars",
    "Linkin Park",
    "Lana Del Rey",
    "Cigarettes After Sex",
]

EXPECTED_TELUGU_ARTISTS = [
    "Anirudh Ravichander",
    "S. P. Balasubrahmanyam",
    "Sid Sriram",
    "Devi Sri Prasad",
    "Thaman S",
    "Vivek Sagar",
    "Mickey J. Meyer",
    "Gopi Sundar",
    "Ram Miriyala",
    "Karthik",
    "Chinmayi",
    "Shreya Ghoshal",
]

EXPECTED_HINDI_ARTISTS = [
    "Arijit Singh",
    "KK",
    "Sonu Nigam",
    "Mohit Chauhan",
    "Atif Aslam",
    "Pritam",
    "Amit Trivedi",
    "Vishal-Shekhar",
    "Shankar-Ehsaan-Loy",
]


@pytest.fixture
def config():
    return LibraryConfig.load()


@pytest.fixture
def matcher(config):
    return ArtistMatcher(config)


def test_artist_counts(config):
    cats = config.raw_config["categories"]
    assert len(cats["International"]["artists"]) == 23
    assert len(cats["Indian/Telugu"]["artists"]) == 12
    assert len(cats["Indian/Hindi"]["artists"]) == 9
    assert len(config.artists) == 44


@pytest.mark.parametrize("artist_name", EXPECTED_INTERNATIONAL_ARTISTS)
def test_all_international_artists_match(matcher, artist_name):
    meta = AudioMetadata(file_path=Path(f"{artist_name} - Song.mp3"), artist=artist_name, title="Song")
    result = matcher.match(meta)
    assert result.matched is True, f"Failed to match {artist_name}"
    assert result.canonical_artist == artist_name
    assert result.category_key == "International"
    assert result.target_subfolder == f"International/{artist_name}"


@pytest.mark.parametrize("artist_name", EXPECTED_TELUGU_ARTISTS)
def test_all_telugu_artists_match(matcher, artist_name):
    meta = AudioMetadata(file_path=Path(f"{artist_name} - Song.mp3"), artist=artist_name, title="Song")
    result = matcher.match(meta)
    assert result.matched is True, f"Failed to match {artist_name}"
    assert result.canonical_artist == artist_name
    assert result.category_key == "Indian/Telugu"
    assert result.target_subfolder == "Indian/Telugu"


@pytest.mark.parametrize("artist_name", EXPECTED_HINDI_ARTISTS)
def test_all_hindi_artists_match(matcher, artist_name):
    meta = AudioMetadata(file_path=Path(f"{artist_name} - Song.mp3"), artist=artist_name, title="Song")
    result = matcher.match(meta)
    assert result.matched is True, f"Failed to match {artist_name}"
    assert result.canonical_artist == artist_name
    assert result.category_key == "Indian/Hindi"
    assert result.target_subfolder == "Indian/Hindi"
