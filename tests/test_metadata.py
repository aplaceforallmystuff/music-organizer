"""Tests for metadata extraction."""

from pathlib import Path
import pytest

from music_organizer.metadata import (
    TrackMetadata,
    _parse_track_number,
    _parse_year,
)
from music_organizer.organizer import sanitize_filename, format_path


class TestTrackMetadata:
    def test_is_complete_with_all_fields(self):
        metadata = TrackMetadata(
            file_path=Path("test.mp3"),
            artist="Artist",
            album="Album",
            title="Title",
        )
        assert metadata.is_complete is True
        assert metadata.missing_fields == []

    def test_is_complete_with_album_artist(self):
        metadata = TrackMetadata(
            file_path=Path("test.mp3"),
            album_artist="Album Artist",
            album="Album",
            title="Title",
        )
        assert metadata.is_complete is True

    def test_is_incomplete_missing_artist(self):
        metadata = TrackMetadata(
            file_path=Path("test.mp3"),
            album="Album",
            title="Title",
        )
        assert metadata.is_complete is False
        assert "artist" in metadata.missing_fields

    def test_effective_artist_prefers_album_artist(self):
        metadata = TrackMetadata(
            file_path=Path("test.mp3"),
            artist="Track Artist",
            album_artist="Album Artist",
        )
        assert metadata.effective_artist == "Album Artist"

    def test_effective_artist_falls_back_to_artist(self):
        metadata = TrackMetadata(
            file_path=Path("test.mp3"),
            artist="Track Artist",
        )
        assert metadata.effective_artist == "Track Artist"


class TestParseTrackNumber:
    def test_simple_number(self):
        track, total = _parse_track_number("5")
        assert track == 5
        assert total is None

    def test_number_with_total(self):
        track, total = _parse_track_number("5/12")
        assert track == 5
        assert total == 12

    def test_list_value(self):
        track, total = _parse_track_number(["3/10"])
        assert track == 3
        assert total == 10

    def test_none_value(self):
        track, total = _parse_track_number(None)
        assert track is None
        assert total is None


class TestParseYear:
    def test_simple_year(self):
        assert _parse_year("2023") == 2023

    def test_full_date(self):
        assert _parse_year("2023-05-15") == 2023

    def test_list_value(self):
        assert _parse_year(["1999"]) == 1999

    def test_none_value(self):
        assert _parse_year(None) is None

    def test_invalid_year(self):
        assert _parse_year("not a year") is None


class TestSanitizeFilename:
    def test_removes_invalid_chars(self):
        assert sanitize_filename("Artist: Name") == "Artist - Name"
        assert sanitize_filename("What?") == "What"
        assert sanitize_filename('Say "Hello"') == "Say 'Hello'"

    def test_handles_slashes(self):
        assert sanitize_filename("AC/DC") == "AC-DC"

    def test_empty_becomes_unknown(self):
        assert sanitize_filename("") == "Unknown"
        assert sanitize_filename("   ") == "Unknown"

    def test_truncates_long_names(self):
        long_name = "A" * 300
        result = sanitize_filename(long_name, max_length=100)
        assert len(result) <= 100


class TestFormatPath:
    def test_basic_format(self):
        metadata = TrackMetadata(
            file_path=Path("test.mp3"),
            artist="Pink Floyd",
            album="The Wall",
            title="Comfortably Numb",
            year=1979,
            track_number=6,
        )
        result = format_path("{artist}/{album} ({year})", metadata)
        assert result == "Pink Floyd/The Wall (1979)"

    def test_format_with_track(self):
        metadata = TrackMetadata(
            file_path=Path("test.mp3"),
            artist="Artist",
            title="Song",
            track_number=3,
        )
        result = format_path("{track:02d} - {title}", metadata)
        assert result == "03 - Song"

    def test_missing_values_use_unknown(self):
        metadata = TrackMetadata(file_path=Path("test.mp3"))
        result = format_path("{artist}/{album}", metadata)
        assert result == "Unknown Artist/Unknown Album"
