"""Configuration settings for the music organizer."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass
class Config:
    """Configuration for music library organization."""

    # Source and destination paths
    source_dir: Path = field(default_factory=lambda: Path("."))
    dest_dir: Path | None = None  # None means organize in-place

    # Folder structure pattern
    # Available placeholders: {artist}, {album}, {year}, {genre}
    folder_pattern: str = "{artist}/{album} ({year})"

    # File naming pattern (None keeps original filename)
    # Available placeholders: {track:02d}, {title}, {artist}, {album}
    file_pattern: str | None = "{track:02d} - {title}"

    # Supported audio formats
    audio_extensions: tuple[str, ...] = (".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".wma")

    # What to do with files missing metadata
    missing_metadata_action: Literal["unsorted", "lookup", "skip"] = "lookup"
    unsorted_folder: str = "_Unsorted"

    # MusicBrainz settings
    musicbrainz_enabled: bool = True
    musicbrainz_user_agent: str = "MusicOrganizer/0.1.0 (https://github.com/user/music-organizer)"

    # AcoustID settings for fingerprinting (requires API key)
    acoustid_api_key: str | None = None

    # Discogs settings (optional - for additional verification)
    discogs_enabled: bool = True
    discogs_token: str | None = None  # Personal access token for higher rate limits

    # Duplicate detection
    detect_duplicates: bool = True
    duplicates_folder: str = "_Duplicates"

    # Compilation handling
    detect_compilations: bool = True
    compilation_folder: str = "_Compilations"  # or "Various Artists"
    compilation_pattern: str = "{compilation_folder}/{album} ({year})"
    soundtrack_folder: str = "Soundtracks"
    soundtrack_pattern: str = "{soundtrack_folder}/{album} ({year})"

    # Artist name normalization
    normalize_artists: bool = True
    learn_artist_names: bool = True  # Learn preferred forms from existing library
    musicbrainz_artist_lookup: bool = False  # Look up canonical names from MusicBrainz (slow)

    # Cleanup settings
    remove_empty_folders: bool = True  # Remove empty artist/album folders after moving

    # Album art settings
    manage_album_art: bool = True
    download_missing_art: bool = True
    art_filename: str = "cover"  # Will add appropriate extension
    art_max_size: int = 1000  # Max dimension in pixels

    # Safety settings
    dry_run: bool = True  # Preview changes without moving files
    create_backup: bool = True
    backup_folder: str = "_Backup"

    # Logging
    log_file: Path | None = None
    verbose: bool = False

    def __post_init__(self):
        if isinstance(self.source_dir, str):
            self.source_dir = Path(self.source_dir)
        if isinstance(self.dest_dir, str):
            self.dest_dir = Path(self.dest_dir)
        if isinstance(self.log_file, str):
            self.log_file = Path(self.log_file)


# Default configuration instance
default_config = Config()
