"""Core organization logic for moving and renaming music files."""

import hashlib
import logging
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from .cache import ScanCache
from .config import Config
from .metadata import TrackMetadata, extract_metadata
from .musicbrainz_lookup import enrich_metadata, init_musicbrainz
from .normalization import ArtistNormalizer, CompilationDetector, detect_album_artists

logger = logging.getLogger("music_organizer")


@dataclass
class FileOperation:
    """Represents a planned file operation."""

    source: Path
    destination: Path
    operation: str  # "move", "copy", "skip", "duplicate"
    reason: str | None = None
    metadata: TrackMetadata | None = None


@dataclass
class OrganizationPlan:
    """Plan for organizing a music library."""

    operations: list[FileOperation] = field(default_factory=list)
    duplicates: list[tuple[Path, Path]] = field(default_factory=list)  # (original, duplicate)
    errors: list[tuple[Path, str]] = field(default_factory=list)
    unsorted: list[Path] = field(default_factory=list)

    @property
    def files_to_move(self) -> int:
        return sum(1 for op in self.operations if op.operation == "move")

    @property
    def files_to_skip(self) -> int:
        return sum(1 for op in self.operations if op.operation == "skip")


def sanitize_filename(name: str, max_length: int = 200) -> str:
    """Sanitize a string for use in file/folder names."""
    if not name:
        return "Unknown"

    # Replace problematic characters
    replacements = {
        "/": "-",
        "\\": "-",
        ":": " -",
        "*": "",
        "?": "",
        '"': "'",
        "<": "",
        ">": "",
        "|": "-",
        "\n": " ",
        "\r": "",
        "\t": " ",
    }

    for old, new in replacements.items():
        name = name.replace(old, new)

    # Remove leading/trailing dots and spaces
    name = name.strip(". ")

    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)

    # Truncate if too long
    if len(name) > max_length:
        name = name[:max_length].strip()

    return name or "Unknown"


def format_path(pattern: str, metadata: TrackMetadata) -> str:
    """Format a path pattern using metadata values."""
    replacements = {
        "{artist}": sanitize_filename(metadata.effective_artist or "Unknown Artist"),
        "{album}": sanitize_filename(metadata.album or "Unknown Album"),
        "{title}": sanitize_filename(metadata.title or metadata.file_path.stem),
        "{year}": str(metadata.year) if metadata.year else "Unknown Year",
        "{genre}": sanitize_filename(metadata.genre or "Unknown Genre"),
        "{track:02d}": f"{metadata.track_number:02d}" if metadata.track_number else "00",
        "{track}": str(metadata.track_number) if metadata.track_number else "0",
        "{disc}": str(metadata.disc_number) if metadata.disc_number else "1",
    }

    result = pattern
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, value)

    return result


def compute_audio_hash(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute a hash of audio file content for duplicate detection.

    Uses first and last chunks plus file size for fast comparison.
    """
    file_size = file_path.stat().st_size
    hasher = hashlib.md5()

    with open(file_path, "rb") as f:
        # Hash first chunk
        hasher.update(f.read(chunk_size))

        # Hash last chunk
        if file_size > chunk_size * 2:
            f.seek(-chunk_size, 2)
            hasher.update(f.read(chunk_size))

        # Include file size
        hasher.update(str(file_size).encode())

    return hasher.hexdigest()


class MusicOrganizer:
    """Organizes music library based on metadata."""

    def __init__(self, config: Config, progress_callback=None):
        """Initialize the organizer.

        Args:
            config: Configuration object
            progress_callback: Optional callback(current, total, path) for progress updates
        """
        self.config = config
        self._hash_cache: dict[str, Path] = {}  # hash -> first seen path
        self._album_artists_cache: dict[Path, list[str]] = {}  # album_dir -> list of artists
        self._progress_callback = progress_callback

        # Initialize scan cache
        cache_dir = config.cache_dir or config.source_dir
        self._scan_cache = ScanCache(cache_dir) if config.use_cache else None

        logger.info(f"Initializing MusicOrganizer with source: {config.source_dir}")
        logger.debug(f"Config: detect_compilations={config.detect_compilations}, normalize_artists={config.normalize_artists}")
        if self._scan_cache:
            logger.info(f"Scan cache enabled ({len(self._scan_cache)} entries loaded)")

        # Initialize external services FIRST so they're available for lookups
        if config.musicbrainz_enabled:
            init_musicbrainz()

        if config.discogs_enabled:
            from .discogs_lookup import init_discogs
            init_discogs(config.discogs_token)

        # Initialize normalization
        self._artist_normalizer = ArtistNormalizer()
        self._compilation_detector = CompilationDetector(
            verify_with_musicbrainz=config.musicbrainz_enabled,
            verify_with_discogs=config.discogs_enabled,
        )

        if config.normalize_artists and config.learn_artist_names:
            logger.info("Learning artist names from existing library...")
            self._artist_normalizer.learn_from_library(config.source_dir)
            learned = len(self._artist_normalizer._learned_names)
            logger.info(f"Learned {learned} artist name forms")

            # Log any variant groups found
            variants = self._artist_normalizer.get_variant_groups()
            if variants:
                logger.info(f"Found {len(variants)} artist name variant groups to merge")

        # Optional: look up canonical artist names from MusicBrainz
        if config.normalize_artists and config.musicbrainz_artist_lookup:
            self._artist_normalizer.learn_from_musicbrainz(config.source_dir)

        if config.detect_compilations:
            logger.info("Scanning for compilation albums...")
            self._compilation_detector.learn_from_library(config.source_dir)

    def scan(self, progress_callback=None) -> OrganizationPlan:
        """Scan the source directory and create an organization plan."""
        plan = OrganizationPlan()

        # Prune cache of missing files
        if self._scan_cache:
            self._scan_cache.prune_missing(self.config.source_dir)

        # Find all audio files
        audio_files = list(self._find_audio_files())
        total_files = len(audio_files)

        for idx, file_path in enumerate(audio_files):
            if progress_callback:
                progress_callback(idx + 1, total_files, file_path)

            try:
                operation = self._plan_file(file_path, plan)
                if operation:
                    plan.operations.append(operation)
            except Exception as e:
                plan.errors.append((file_path, str(e)))

        # Save cache after scan completes
        if self._scan_cache:
            self._scan_cache.save()
            stats = self._scan_cache.get_stats()
            logger.info(f"Cache stats: {stats['hits']} hits, {stats['misses']} misses, {stats['stale']} stale")

        return plan

    def _find_audio_files(self):
        """Yield all audio files in the source directory."""
        for ext in self.config.audio_extensions:
            yield from self.config.source_dir.rglob(f"*{ext}")
            yield from self.config.source_dir.rglob(f"*{ext.upper()}")

    def _plan_file(self, file_path: Path, plan: OrganizationPlan) -> FileOperation | None:
        """Create a plan for a single file."""
        # Skip files in special folders
        if any(
            part.startswith("_") for part in file_path.relative_to(self.config.source_dir).parts
        ):
            return None

        # Check cache first
        cached = self._scan_cache.get(file_path) if self._scan_cache else None

        if cached:
            # Rebuild TrackMetadata from cache
            metadata = TrackMetadata(
                file_path=file_path,
                artist=cached.artist,
                album_artist=cached.album_artist,
                album=cached.album,
                title=cached.title,
                track_number=cached.track_number,
                year=cached.year,
            )
            # Restore hash if we had it
            if cached.content_hash:
                self._hash_cache[cached.content_hash] = file_path
        else:
            # Extract metadata fresh
            metadata = extract_metadata(file_path)

            # Try to enrich missing metadata
            if not metadata.is_complete and self.config.missing_metadata_action == "lookup":
                if self.config.musicbrainz_enabled:
                    metadata = enrich_metadata(metadata, self.config.acoustid_api_key)

            # Compute hash for duplicate detection (will cache it)
            content_hash = None
            if self.config.detect_duplicates:
                content_hash = compute_audio_hash(file_path)

            # Cache the result
            if self._scan_cache:
                self._scan_cache.set(
                    file_path=file_path,
                    artist=metadata.artist,
                    album_artist=metadata.album_artist,
                    album=metadata.album,
                    title=metadata.title,
                    track_number=metadata.track_number,
                    year=metadata.year,
                    is_complete=metadata.is_complete,
                    content_hash=content_hash,
                )

        # Check for duplicates
        if self.config.detect_duplicates:
            # Use cached hash or compute fresh
            if cached and cached.content_hash:
                file_hash = cached.content_hash
            else:
                file_hash = compute_audio_hash(file_path)

            if file_hash in self._hash_cache:
                original = self._hash_cache[file_hash]
                # Don't mark as duplicate if it's the same file
                if original != file_path:
                    plan.duplicates.append((original, file_path))
                    return FileOperation(
                        source=file_path,
                        destination=self._get_duplicate_path(file_path),
                        operation="duplicate",
                        reason=f"Duplicate of {original}",
                        metadata=metadata,
                    )
            self._hash_cache[file_hash] = file_path

        # Handle files with missing metadata
        if not metadata.is_complete:
            if self.config.missing_metadata_action == "skip":
                return FileOperation(
                    source=file_path,
                    destination=file_path,
                    operation="skip",
                    reason=f"Missing: {', '.join(metadata.missing_fields)}",
                    metadata=metadata,
                )
            elif self.config.missing_metadata_action in ("unsorted", "lookup"):
                plan.unsorted.append(file_path)
                return FileOperation(
                    source=file_path,
                    destination=self._get_unsorted_path(file_path),
                    operation="move",
                    reason=f"Missing: {', '.join(metadata.missing_fields)}",
                    metadata=metadata,
                )

        # Calculate destination path
        dest_path = self._calculate_destination(metadata)

        # Skip if already in correct location
        if file_path == dest_path:
            return FileOperation(
                source=file_path,
                destination=dest_path,
                operation="skip",
                reason="Already organized",
                metadata=metadata,
            )

        return FileOperation(
            source=file_path,
            destination=dest_path,
            operation="move",
            metadata=metadata,
        )

    def _calculate_destination(self, metadata: TrackMetadata) -> Path:
        """Calculate the destination path for a file."""
        base_dir = self.config.dest_dir or self.config.source_dir

        # Normalize artist name if enabled
        original_artist = metadata.effective_artist
        artist = original_artist
        if self.config.normalize_artists and artist:
            artist = self._artist_normalizer.normalize(artist)
            if artist != original_artist:
                logger.debug(f"Normalized artist: '{original_artist}' -> '{artist}'")

        # Check if this is a compilation or soundtrack
        is_compilation = False
        is_soundtrack = False

        if self.config.detect_compilations:
            # Get all artists from this album folder for better detection
            album_dir = metadata.file_path.parent
            if album_dir not in self._album_artists_cache:
                self._album_artists_cache[album_dir] = detect_album_artists(
                    self.config.source_dir, album_dir
                )
            track_artists = self._album_artists_cache[album_dir]

            is_compilation = self._compilation_detector.is_compilation(
                album_artist=metadata.album_artist,
                artist=metadata.artist,
                album=metadata.album,
                track_artists=track_artists,
            )

            is_soundtrack = self._compilation_detector.is_soundtrack(
                album=metadata.album,
                album_artist=metadata.album_artist,
            )

            if is_compilation:
                logger.debug(f"Detected COMPILATION: album='{metadata.album}', album_artist='{metadata.album_artist}', track_artists={len(track_artists)} unique")
            if is_soundtrack:
                logger.debug(f"Detected SOUNDTRACK: album='{metadata.album}'")

        # Choose the appropriate pattern
        if is_soundtrack:
            pattern = self.config.soundtrack_pattern
            folder_path = pattern.replace("{soundtrack_folder}", self.config.soundtrack_folder)
            logger.debug(f"Using soundtrack pattern: {pattern}")
        elif is_compilation:
            pattern = self.config.compilation_pattern
            folder_path = pattern.replace("{compilation_folder}", self.config.compilation_folder)
            logger.debug(f"Using compilation pattern: {pattern}")
        else:
            pattern = self.config.folder_pattern
            folder_path = pattern

        # Create modified metadata with normalized artist for formatting
        format_replacements = {
            "{artist}": sanitize_filename(artist or "Unknown Artist"),
            "{album}": sanitize_filename(metadata.album or "Unknown Album"),
            "{title}": sanitize_filename(metadata.title or metadata.file_path.stem),
            "{year}": str(metadata.year) if metadata.year else "Unknown Year",
            "{genre}": sanitize_filename(metadata.genre or "Unknown Genre"),
            "{track:02d}": f"{metadata.track_number:02d}" if metadata.track_number else "00",
            "{track}": str(metadata.track_number) if metadata.track_number else "0",
            "{disc}": str(metadata.disc_number) if metadata.disc_number else "1",
        }

        for placeholder, value in format_replacements.items():
            folder_path = folder_path.replace(placeholder, value)

        # Format filename
        if self.config.file_pattern:
            filename = self.config.file_pattern
            for placeholder, value in format_replacements.items():
                filename = filename.replace(placeholder, value)
            filename += metadata.file_path.suffix.lower()
        else:
            filename = metadata.file_path.name

        return base_dir / folder_path / filename

    def _get_unsorted_path(self, file_path: Path) -> Path:
        """Get path in the unsorted folder."""
        base_dir = self.config.dest_dir or self.config.source_dir
        return base_dir / self.config.unsorted_folder / file_path.name

    def _get_duplicate_path(self, file_path: Path) -> Path:
        """Get path in the duplicates folder."""
        base_dir = self.config.dest_dir or self.config.source_dir
        return base_dir / self.config.duplicates_folder / file_path.name

    def execute(self, plan: OrganizationPlan, progress_callback=None) -> tuple[int, int]:
        """Execute the organization plan.

        Returns (successful_moves, failed_moves).
        """
        if self.config.dry_run:
            raise RuntimeError("Cannot execute in dry-run mode. Set dry_run=False to proceed.")

        successful = 0
        failed = 0

        # Track directories that might become empty
        dirs_to_check: set[Path] = set()

        operations = [op for op in plan.operations if op.operation in ("move", "duplicate")]
        total = len(operations)

        for idx, operation in enumerate(operations):
            if progress_callback:
                progress_callback(idx + 1, total, operation.source)

            try:
                # Track source directory for cleanup
                dirs_to_check.add(operation.source.parent)
                dirs_to_check.add(operation.source.parent.parent)  # Artist folder

                self._execute_operation(operation)
                successful += 1
            except Exception as e:
                plan.errors.append((operation.source, str(e)))
                failed += 1

        # Clean up empty folders
        if self.config.remove_empty_folders:
            self._cleanup_empty_folders(dirs_to_check)

        return successful, failed

    def _cleanup_empty_folders(self, dirs_to_check: set[Path]):
        """Remove empty album and artist folders after moving files."""
        # Sort by depth (deepest first) to clean up from bottom up
        sorted_dirs = sorted(dirs_to_check, key=lambda p: len(p.parts), reverse=True)
        removed_count = 0

        for dir_path in sorted_dirs:
            if not dir_path.exists():
                continue

            # Don't delete the source dir itself or special folders
            if dir_path == self.config.source_dir:
                continue
            if dir_path.name.startswith(("_", ".")):
                continue

            # Check if directory is empty (or only contains hidden files like .DS_Store)
            try:
                contents = list(dir_path.iterdir())
                visible_contents = [f for f in contents if not f.name.startswith(".")]

                if not visible_contents:
                    # Remove hidden files first
                    for hidden in contents:
                        try:
                            hidden.unlink()
                        except Exception:
                            pass

                    # Remove the directory
                    dir_path.rmdir()
                    removed_count += 1
                    logger.debug(f"Removed empty folder: {dir_path}")
            except OSError:
                pass  # Directory not empty or permission denied

        if removed_count:
            logger.info(f"Removed {removed_count} empty folders")

    def _execute_operation(self, operation: FileOperation):
        """Execute a single file operation."""
        # Create destination directory
        operation.destination.parent.mkdir(parents=True, exist_ok=True)

        # Handle filename collisions
        dest_path = operation.destination
        counter = 1
        while dest_path.exists():
            stem = operation.destination.stem
            suffix = operation.destination.suffix
            dest_path = operation.destination.parent / f"{stem} ({counter}){suffix}"
            counter += 1

        # Move the file
        shutil.move(str(operation.source), str(dest_path))

        # Move associated files (artwork, cue sheets, etc.)
        self._move_associated_files(operation.source, dest_path)

    def _move_associated_files(self, source: Path, dest: Path):
        """Move associated files like album art, cue sheets, logs."""
        source_dir = source.parent
        dest_dir = dest.parent

        # Common associated file patterns
        associated_patterns = [
            "cover.*", "folder.*", "album.*", "front.*",  # Album art
            "*.cue", "*.log", "*.m3u", "*.m3u8",  # Playlists and logs
            "*.txt", "*.nfo",  # Info files
        ]

        # Only move if this is the last audio file leaving the source directory
        remaining_audio = [
            f for f in source_dir.iterdir()
            if f.suffix.lower() in self.config.audio_extensions
        ]

        if not remaining_audio:
            for pattern in associated_patterns:
                for file_path in source_dir.glob(pattern):
                    dest_file = dest_dir / file_path.name
                    if not dest_file.exists():
                        shutil.move(str(file_path), str(dest_file))

            # Clean up empty source directory
            try:
                source_dir.rmdir()
            except OSError:
                pass  # Directory not empty
