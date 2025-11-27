"""Album art management - download, embed, and organize cover art."""

import io
from pathlib import Path

import requests
from PIL import Image

from .metadata import TrackMetadata, extract_metadata
from .musicbrainz_lookup import get_album_art_url, lookup_by_metadata


# Common album art filenames to look for
ART_FILENAMES = [
    "cover", "folder", "album", "front", "albumart",
    "Cover", "Folder", "Album", "Front", "AlbumArt",
]
ART_EXTENSIONS = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"]


def find_existing_art(directory: Path) -> Path | None:
    """Find existing album art in a directory."""
    for name in ART_FILENAMES:
        for ext in ART_EXTENSIONS:
            art_path = directory / f"{name}{ext}"
            if art_path.exists():
                return art_path

    # Also check for any image files
    for ext in ART_EXTENSIONS:
        images = list(directory.glob(f"*{ext}"))
        if images:
            return images[0]

    return None


def download_album_art(
    artist: str,
    album: str,
    dest_path: Path,
    max_size: int = 1000,
) -> bool:
    """Download album art from Cover Art Archive.

    Returns True if successful.
    """
    # Look up the release on MusicBrainz
    result = lookup_by_metadata(artist=artist, album=album)
    if not result or not result.musicbrainz_release_id:
        return False

    # Get cover art URL
    art_url = get_album_art_url(result.musicbrainz_release_id)
    if not art_url:
        return False

    try:
        # Download the image
        response = requests.get(art_url, timeout=30)
        response.raise_for_status()

        # Process and save the image
        image = Image.open(io.BytesIO(response.content))

        # Resize if too large
        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        # Convert to RGB if necessary (for JPEG)
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        # Determine format from destination path
        suffix = dest_path.suffix.lower()
        if suffix in (".jpg", ".jpeg"):
            image.save(dest_path, "JPEG", quality=90)
        elif suffix == ".png":
            image.save(dest_path, "PNG")
        else:
            # Default to JPEG
            dest_path = dest_path.with_suffix(".jpg")
            image.save(dest_path, "JPEG", quality=90)

        return True

    except Exception:
        return False


def extract_embedded_art(file_path: Path, dest_path: Path) -> bool:
    """Extract embedded album art from an audio file.

    Returns True if successful.
    """
    try:
        import mutagen
        from mutagen.flac import FLAC
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4

        audio = mutagen.File(file_path)
        if audio is None:
            return False

        image_data = None

        # Extract from FLAC
        if isinstance(audio, FLAC) and audio.pictures:
            image_data = audio.pictures[0].data

        # Extract from MP3 (ID3)
        elif hasattr(audio, "tags") and audio.tags:
            if isinstance(audio.tags, ID3):
                for key in audio.tags:
                    if key.startswith("APIC"):
                        image_data = audio.tags[key].data
                        break

        # Extract from MP4/M4A
        elif isinstance(audio, MP4):
            if "covr" in audio.tags:
                image_data = bytes(audio.tags["covr"][0])

        if image_data:
            # Save the image
            image = Image.open(io.BytesIO(image_data))
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            image.save(dest_path.with_suffix(".jpg"), "JPEG", quality=90)
            return True

    except Exception:
        pass

    return False


def standardize_album_art(
    directory: Path,
    target_name: str = "cover",
    max_size: int = 1000,
) -> Path | None:
    """Standardize album art in a directory.

    - Finds existing art or extracts from audio files
    - Renames to standard filename
    - Resizes if too large

    Returns path to the standardized art file, or None if no art found.
    """
    art_path = find_existing_art(directory)

    # If no art file found, try to extract from audio files
    if not art_path:
        for file_path in directory.iterdir():
            if file_path.suffix.lower() in (".mp3", ".flac", ".m4a"):
                target_path = directory / f"{target_name}.jpg"
                if extract_embedded_art(file_path, target_path):
                    art_path = target_path
                    break

    if not art_path:
        return None

    # Standardize the file
    try:
        image = Image.open(art_path)

        # Resize if needed
        if max(image.size) > max_size:
            image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

        # Convert and save with standard name
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        target_path = directory / f"{target_name}.jpg"
        image.save(target_path, "JPEG", quality=90)

        # Remove old file if we renamed it
        if art_path != target_path and art_path.exists():
            art_path.unlink()

        return target_path

    except Exception:
        return art_path  # Return original if processing fails


class AlbumArtManager:
    """Manages album art for a music library."""

    def __init__(
        self,
        download_missing: bool = True,
        max_size: int = 1000,
        art_filename: str = "cover",
    ):
        self.download_missing = download_missing
        self.max_size = max_size
        self.art_filename = art_filename

    def process_directory(self, directory: Path) -> dict:
        """Process album art for a directory.

        Returns a dict with:
        - found: bool - whether art was found/created
        - source: str - where the art came from
        - path: Path | None - path to the art file
        """
        result = {"found": False, "source": None, "path": None}

        # First, check for existing art
        existing = find_existing_art(directory)
        if existing:
            # Standardize it
            standardized = standardize_album_art(
                directory, self.art_filename, self.max_size
            )
            result["found"] = True
            result["source"] = "existing"
            result["path"] = standardized
            return result

        # Try to extract from audio files
        for file_path in directory.iterdir():
            if file_path.suffix.lower() in (".mp3", ".flac", ".m4a"):
                target = directory / f"{self.art_filename}.jpg"
                if extract_embedded_art(file_path, target):
                    result["found"] = True
                    result["source"] = "embedded"
                    result["path"] = target
                    return result

        # Try to download if enabled
        if self.download_missing:
            # Get metadata from first audio file
            for file_path in directory.iterdir():
                if file_path.suffix.lower() in (".mp3", ".flac", ".m4a", ".ogg"):
                    metadata = extract_metadata(file_path)
                    if metadata.effective_artist and metadata.album:
                        target = directory / f"{self.art_filename}.jpg"
                        if download_album_art(
                            metadata.effective_artist,
                            metadata.album,
                            target,
                            self.max_size,
                        ):
                            result["found"] = True
                            result["source"] = "downloaded"
                            result["path"] = target
                            return result
                    break

        return result

    def scan_library(self, root_dir: Path, progress_callback=None) -> dict:
        """Scan entire library and process album art.

        Returns summary statistics.
        """
        stats = {
            "total_albums": 0,
            "with_art": 0,
            "art_added": 0,
            "art_downloaded": 0,
            "missing_art": 0,
        }

        # Find all directories containing audio files
        album_dirs = set()
        for ext in (".mp3", ".flac", ".m4a", ".ogg"):
            for file_path in root_dir.rglob(f"*{ext}"):
                album_dirs.add(file_path.parent)

        album_dirs = sorted(album_dirs)
        total = len(album_dirs)

        for idx, directory in enumerate(album_dirs):
            if progress_callback:
                progress_callback(idx + 1, total, directory)

            stats["total_albums"] += 1

            result = self.process_directory(directory)

            if result["found"]:
                stats["with_art"] += 1
                if result["source"] in ("embedded", "downloaded"):
                    stats["art_added"] += 1
                if result["source"] == "downloaded":
                    stats["art_downloaded"] += 1
            else:
                stats["missing_art"] += 1

        return stats
