"""Scan cache to avoid re-processing unchanged files."""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("music_organizer")

CACHE_VERSION = 1
CACHE_FILENAME = ".music-organizer-cache.json"


@dataclass
class CachedFile:
    """Cached metadata for a single file."""

    path: str
    mtime: float  # File modification time
    size: int  # File size in bytes
    artist: str | None
    album_artist: str | None
    album: str | None
    title: str | None
    track_number: int | None
    year: int | None
    is_complete: bool
    content_hash: str | None = None  # For duplicate detection
    scanned_at: str | None = None  # ISO timestamp of when we scanned it

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CachedFile":
        return cls(**data)


class ScanCache:
    """Persistent cache for scanned file metadata.

    Stores metadata keyed by file path with modification time tracking.
    Only re-scans files that have changed since last scan.
    """

    def __init__(self, cache_dir: Path):
        """Initialize the cache.

        Args:
            cache_dir: Directory to store the cache file (typically the music library root)
        """
        self.cache_file = cache_dir / CACHE_FILENAME
        self._cache: dict[str, CachedFile] = {}
        self._dirty = False
        self._stats = {"hits": 0, "misses": 0, "stale": 0}
        self._load()

    def _load(self):
        """Load cache from disk."""
        if not self.cache_file.exists():
            logger.debug("No existing cache found, starting fresh")
            return

        try:
            with open(self.cache_file, "r") as f:
                data = json.load(f)

            # Check version compatibility
            if data.get("version") != CACHE_VERSION:
                logger.info(f"Cache version mismatch (got {data.get('version')}, expected {CACHE_VERSION}), rebuilding")
                return

            # Load entries
            for path, entry_data in data.get("files", {}).items():
                try:
                    self._cache[path] = CachedFile.from_dict(entry_data)
                except (TypeError, KeyError) as e:
                    logger.debug(f"Skipping invalid cache entry {path}: {e}")

            logger.info(f"Loaded {len(self._cache)} entries from cache")

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to load cache: {e}, starting fresh")
            self._cache = {}

    def save(self):
        """Save cache to disk."""
        if not self._dirty:
            logger.debug("Cache unchanged, skipping save")
            return

        data = {
            "version": CACHE_VERSION,
            "saved_at": datetime.now().isoformat(),
            "files": {path: entry.to_dict() for path, entry in self._cache.items()},
        }

        try:
            with open(self.cache_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved {len(self._cache)} entries to cache")
            self._dirty = False
        except OSError as e:
            logger.warning(f"Failed to save cache: {e}")

    def get(self, file_path: Path) -> CachedFile | None:
        """Get cached metadata for a file if still valid.

        Returns None if:
        - File not in cache
        - File has been modified since caching
        - File size has changed
        """
        path_str = str(file_path)

        if path_str not in self._cache:
            self._stats["misses"] += 1
            return None

        cached = self._cache[path_str]

        # Check if file still exists and hasn't changed
        try:
            stat = file_path.stat()
            if stat.st_mtime != cached.mtime or stat.st_size != cached.size:
                self._stats["stale"] += 1
                logger.debug(f"Cache stale for {file_path.name} (mtime/size changed)")
                return None
        except OSError:
            # File doesn't exist anymore
            self._stats["misses"] += 1
            return None

        self._stats["hits"] += 1
        return cached

    def set(
        self,
        file_path: Path,
        artist: str | None,
        album_artist: str | None,
        album: str | None,
        title: str | None,
        track_number: int | None,
        year: int | None,
        is_complete: bool,
        content_hash: str | None = None,
    ):
        """Cache metadata for a file."""
        try:
            stat = file_path.stat()
        except OSError:
            return  # Can't cache if we can't stat

        entry = CachedFile(
            path=str(file_path),
            mtime=stat.st_mtime,
            size=stat.st_size,
            artist=artist,
            album_artist=album_artist,
            album=album,
            title=title,
            track_number=track_number,
            year=year,
            is_complete=is_complete,
            content_hash=content_hash,
            scanned_at=datetime.now().isoformat(),
        )

        self._cache[str(file_path)] = entry
        self._dirty = True

    def remove(self, file_path: Path):
        """Remove a file from the cache."""
        path_str = str(file_path)
        if path_str in self._cache:
            del self._cache[path_str]
            self._dirty = True

    def clear(self):
        """Clear all cache entries."""
        self._cache = {}
        self._dirty = True
        logger.info("Cache cleared")

    def get_stats(self) -> dict[str, int]:
        """Get cache hit/miss statistics."""
        return {
            "total_cached": len(self._cache),
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "stale": self._stats["stale"],
        }

    def prune_missing(self, source_dir: Path):
        """Remove cache entries for files that no longer exist."""
        to_remove = []

        for path_str in self._cache:
            path = Path(path_str)
            # Only prune if it was under the source directory
            try:
                path.relative_to(source_dir)
                if not path.exists():
                    to_remove.append(path_str)
            except ValueError:
                # Not under source_dir, skip
                pass

        for path_str in to_remove:
            del self._cache[path_str]

        if to_remove:
            self._dirty = True
            logger.info(f"Pruned {len(to_remove)} missing files from cache")

    def __len__(self) -> int:
        return len(self._cache)

    def __contains__(self, file_path: Path) -> bool:
        return str(file_path) in self._cache
