import pytest
from music_agent.sanitizer import sanitize_filename, sanitize_folder_path


def test_sanitize_filename_illegal_chars():
    dirty = 'Billie Eilish: "Ocean Eyes" / Live *2020? <HQ> | [320kbps].mp3'
    cleaned = sanitize_filename(dirty)
    for bad_char in [':', '"', '/', '*', '?', '<', '>', '|']:
        assert bad_char not in cleaned
    assert cleaned.endswith(".mp3")


def test_sanitize_filename_dots_and_spaces():
    dirty = "  ...Track Title...  .flac"
    cleaned = sanitize_filename(dirty)
    assert not cleaned.startswith(".")
    assert not cleaned.startswith(" ")
    assert cleaned.endswith(".flac")


def test_sanitize_filename_reserved_windows_names():
    cleaned = sanitize_filename("CON.mp3")
    assert cleaned == "_CON.mp3"
    cleaned_aux = sanitize_filename("aux.flac")
    assert cleaned_aux == "_aux.flac"


def test_sanitize_filename_max_length():
    long_title = "A" * 250 + ".mp3"
    cleaned = sanitize_filename(long_title, max_length=50)
    assert len(cleaned) <= 50
    assert cleaned.endswith(".mp3")


def test_sanitize_folder_path():
    path_str = "International/Billie: Eilish/Live *Shows?"
    sanitized = sanitize_folder_path(path_str)
    assert ":" not in sanitized
    assert "*" not in sanitized
    assert "?" not in sanitized
    assert sanitized.startswith("International/Billie Eilish")
