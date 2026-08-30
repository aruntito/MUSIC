import pytest
from pathlib import Path
from music_agent.metadata import read_audio_metadata, extract_metadata_from_filename
from tests.make_dummy_audio import create_dummy_mp3, create_dummy_flac, create_dummy_wav, create_dummy_m4a


def test_filename_fallback_extraction():
    p1 = Path("Billie Eilish - Ocean Eyes.mp3")
    art, title = extract_metadata_from_filename(p1)
    assert art == "Billie Eilish"
    assert title == "Ocean Eyes"

    p2 = Path("01. Wiz Khalifa - See You Again [Official Audio].m4a")
    art2, title2 = extract_metadata_from_filename(p2)
    assert art2 == "Wiz Khalifa"
    assert title2 == "See You Again"

    p3 = Path("Kesariya.flac")
    art3, title3 = extract_metadata_from_filename(p3)
    assert art3 is None
    assert title3 == "Kesariya"


def test_embedded_metadata_extraction_mp3(tmp_path):
    mp3_file = tmp_path / "test_song.mp3"
    create_dummy_mp3(
        mp3_file,
        artist="Billie Eilish",
        title="Bad Guy",
        album="When We All Fall Asleep",
        album_artist="Billie Eilish",
        track_num="2"
    )

    meta = read_audio_metadata(mp3_file)
    assert meta.has_embedded_metadata is True
    assert meta.artist == "Billie Eilish"
    assert meta.title == "Bad Guy"
    assert meta.album == "When We All Fall Asleep"
    assert meta.track_number == "2"


def test_embedded_metadata_extraction_flac(tmp_path):
    flac_file = tmp_path / "test_flac.flac"
    create_dummy_flac(
        flac_file,
        artist="Anirudh Ravichander",
        title="Hukum",
        album="Jailer"
    )

    meta = read_audio_metadata(flac_file)
    assert meta.has_embedded_metadata is True
    assert meta.artist == "Anirudh Ravichander"
    assert meta.title == "Hukum"


def test_fallback_when_tags_missing(tmp_path):
    # File with no embedded ID3 tags, but standard filename
    mp3_file = tmp_path / "Sid Sriram - Samajavaragamana.mp3"
    create_dummy_mp3(mp3_file)  # No tags

    meta = read_audio_metadata(mp3_file)
    assert meta.has_embedded_metadata is False
    assert meta.metadata_source == "filename"
    assert meta.artist == "Sid Sriram"
    assert meta.title == "Samajavaragamana"
