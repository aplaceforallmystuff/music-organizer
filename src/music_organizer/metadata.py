"""Audio metadata extraction using mutagen."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.oggvorbis import OggVorbis


@dataclass
class TrackMetadata:
    """Metadata extracted from an audio file."""

    file_path: Path
    artist: str | None = None
    album_artist: str | None = None
    album: str | None = None
    title: str | None = None
    track_number: int | None = None
    track_total: int | None = None
    disc_number: int | None = None
    disc_total: int | None = None
    year: int | None = None
    genre: str | None = None
    duration: float | None = None  # seconds
    bitrate: int | None = None  # kbps
    sample_rate: int | None = None  # Hz
    channels: int | None = None
    format: str | None = None
    has_album_art: bool = False

    @property
    def effective_artist(self) -> str | None:
        """Return album artist if available, otherwise artist."""
        return self.album_artist or self.artist

    @property
    def is_complete(self) -> bool:
        """Check if essential metadata is present."""
        return all([self.artist or self.album_artist, self.album, self.title])

    @property
    def missing_fields(self) -> list[str]:
        """List of essential fields that are missing."""
        missing = []
        if not (self.artist or self.album_artist):
            missing.append("artist")
        if not self.album:
            missing.append("album")
        if not self.title:
            missing.append("title")
        return missing


def _get_first(values: Any) -> str | None:
    """Extract first value from a list or return the value itself."""
    if values is None:
        return None
    if isinstance(values, list):
        return str(values[0]) if values else None
    return str(values)


def _parse_track_number(value: Any) -> tuple[int | None, int | None]:
    """Parse track number which may be in 'X/Y' format."""
    if value is None:
        return None, None

    text = _get_first(value)
    if text is None:
        return None, None

    if "/" in text:
        parts = text.split("/")
        try:
            track = int(parts[0])
            total = int(parts[1]) if len(parts) > 1 else None
            return track, total
        except ValueError:
            return None, None
    try:
        return int(text), None
    except ValueError:
        return None, None


def _parse_year(value: Any) -> int | None:
    """Parse year from various date formats."""
    text = _get_first(value)
    if text is None:
        return None

    # Handle full date formats like "2023-01-15"
    if "-" in text:
        text = text.split("-")[0]

    try:
        year = int(text[:4])  # Take first 4 digits
        if 1900 <= year <= 2100:
            return year
    except (ValueError, IndexError):
        pass
    return None


def extract_metadata(file_path: Path) -> TrackMetadata:
    """Extract metadata from an audio file."""
    metadata = TrackMetadata(file_path=file_path)

    try:
        audio = mutagen.File(file_path)
        if audio is None:
            return metadata

        metadata.format = type(audio).__name__
        metadata.duration = audio.info.length if hasattr(audio.info, "length") else None

        # Get audio quality info
        if hasattr(audio.info, "bitrate"):
            metadata.bitrate = audio.info.bitrate // 1000 if audio.info.bitrate else None
        if hasattr(audio.info, "sample_rate"):
            metadata.sample_rate = audio.info.sample_rate
        if hasattr(audio.info, "channels"):
            metadata.channels = audio.info.channels

        # Extract tags based on file type
        if isinstance(audio, MP3):
            metadata = _extract_id3_tags(audio, metadata)
        elif isinstance(audio, FLAC):
            metadata = _extract_vorbis_tags(audio, metadata)
            metadata.has_album_art = len(audio.pictures) > 0
        elif isinstance(audio, OggVorbis):
            metadata = _extract_vorbis_tags(audio, metadata)
        elif isinstance(audio, MP4):
            metadata = _extract_mp4_tags(audio, metadata)
        else:
            # Try EasyID3-style access for other formats
            metadata = _extract_generic_tags(audio, metadata)

    except Exception:
        # Return partial metadata on error
        pass

    return metadata


def _extract_id3_tags(audio: MP3, metadata: TrackMetadata) -> TrackMetadata:
    """Extract tags from MP3 files with ID3 tags."""
    try:
        tags = EasyID3(audio.filename)
    except Exception:
        tags = audio.tags or {}

    metadata.artist = _get_first(tags.get("artist"))
    metadata.album_artist = _get_first(tags.get("albumartist") or tags.get("performer"))
    metadata.album = _get_first(tags.get("album"))
    metadata.title = _get_first(tags.get("title"))
    metadata.genre = _get_first(tags.get("genre"))

    track, total = _parse_track_number(tags.get("tracknumber"))
    metadata.track_number = track
    metadata.track_total = total

    disc, disc_total = _parse_track_number(tags.get("discnumber"))
    metadata.disc_number = disc
    metadata.disc_total = disc_total

    metadata.year = _parse_year(tags.get("date") or tags.get("year"))

    # Check for album art in ID3 tags
    if audio.tags:
        metadata.has_album_art = any(
            key.startswith("APIC") for key in audio.tags.keys()
        )

    return metadata


def _extract_vorbis_tags(audio: mutagen.FileType, metadata: TrackMetadata) -> TrackMetadata:
    """Extract Vorbis comments (FLAC, OGG)."""
    tags = audio.tags or {}

    metadata.artist = _get_first(tags.get("artist"))
    metadata.album_artist = _get_first(tags.get("albumartist"))
    metadata.album = _get_first(tags.get("album"))
    metadata.title = _get_first(tags.get("title"))
    metadata.genre = _get_first(tags.get("genre"))

    track, total = _parse_track_number(tags.get("tracknumber"))
    metadata.track_number = track
    metadata.track_total = _parse_track_number(tags.get("tracktotal"))[0] or total

    disc, disc_total = _parse_track_number(tags.get("discnumber"))
    metadata.disc_number = disc
    metadata.disc_total = _parse_track_number(tags.get("disctotal"))[0] or disc_total

    metadata.year = _parse_year(tags.get("date") or tags.get("year"))

    return metadata


def _extract_mp4_tags(audio: MP4, metadata: TrackMetadata) -> TrackMetadata:
    """Extract tags from MP4/M4A files."""
    tags = audio.tags or {}

    metadata.artist = _get_first(tags.get("\xa9ART"))
    metadata.album_artist = _get_first(tags.get("aART"))
    metadata.album = _get_first(tags.get("\xa9alb"))
    metadata.title = _get_first(tags.get("\xa9nam"))
    metadata.genre = _get_first(tags.get("\xa9gen"))

    # MP4 track/disc numbers are tuples: (number, total)
    trkn = tags.get("trkn")
    if trkn and isinstance(trkn, list) and trkn[0]:
        metadata.track_number = trkn[0][0]
        metadata.track_total = trkn[0][1] if len(trkn[0]) > 1 else None

    disk = tags.get("disk")
    if disk and isinstance(disk, list) and disk[0]:
        metadata.disc_number = disk[0][0]
        metadata.disc_total = disk[0][1] if len(disk[0]) > 1 else None

    metadata.year = _parse_year(tags.get("\xa9day"))

    # Check for album art
    metadata.has_album_art = "covr" in tags

    return metadata


def _extract_generic_tags(audio: mutagen.FileType, metadata: TrackMetadata) -> TrackMetadata:
    """Fallback tag extraction for other formats."""
    tags = audio.tags or {}

    # Try common tag names
    for artist_key in ["artist", "ARTIST", "Author"]:
        if artist_key in tags:
            metadata.artist = _get_first(tags[artist_key])
            break

    for album_key in ["album", "ALBUM", "WM/AlbumTitle"]:
        if album_key in tags:
            metadata.album = _get_first(tags[album_key])
            break

    for title_key in ["title", "TITLE", "Title"]:
        if title_key in tags:
            metadata.title = _get_first(tags[title_key])
            break

    return metadata


def scan_directory(
    directory: Path, extensions: tuple[str, ...] = (".mp3", ".flac", ".m4a", ".ogg")
) -> list[TrackMetadata]:
    """Scan a directory recursively and extract metadata from all audio files."""
    results = []

    for file_path in directory.rglob("*"):
        if file_path.suffix.lower() in extensions:
            metadata = extract_metadata(file_path)
            results.append(metadata)

    return results
