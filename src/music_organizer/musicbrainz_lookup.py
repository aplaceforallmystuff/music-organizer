"""MusicBrainz integration for metadata lookup."""

import time
from dataclasses import dataclass
from pathlib import Path

import musicbrainzngs

from .metadata import TrackMetadata

# Rate limiting: MusicBrainz requires 1 request per second max
_last_request_time: float = 0
_MIN_REQUEST_INTERVAL = 1.1  # seconds


def _rate_limit():
    """Ensure we don't exceed MusicBrainz rate limits."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def init_musicbrainz(app_name: str = "MusicOrganizer", version: str = "0.1.0", contact: str = ""):
    """Initialize MusicBrainz client with user agent."""
    musicbrainzngs.set_useragent(app_name, version, contact)


@dataclass
class MusicBrainzResult:
    """Result from a MusicBrainz lookup."""

    artist: str | None = None
    album: str | None = None
    title: str | None = None
    year: int | None = None
    track_number: int | None = None
    track_total: int | None = None
    genre: str | None = None
    musicbrainz_recording_id: str | None = None
    musicbrainz_release_id: str | None = None
    confidence: float = 0.0  # 0-1 score


def lookup_by_metadata(
    artist: str | None = None,
    album: str | None = None,
    title: str | None = None,
    duration_ms: int | None = None,
) -> MusicBrainzResult | None:
    """Look up track info using existing metadata."""
    if not any([artist, album, title]):
        return None

    _rate_limit()

    try:
        # Build search query
        query_parts = []
        if title:
            query_parts.append(f'recording:"{title}"')
        if artist:
            query_parts.append(f'artist:"{artist}"')
        if album:
            query_parts.append(f'release:"{album}"')

        query = " AND ".join(query_parts)

        result = musicbrainzngs.search_recordings(
            query=query,
            limit=5,
        )

        recordings = result.get("recording-list", [])
        if not recordings:
            return None

        # Find best match
        best_match = recordings[0]
        score = int(best_match.get("ext:score", 0))

        # Extract data from the recording
        mb_result = MusicBrainzResult(
            title=best_match.get("title"),
            musicbrainz_recording_id=best_match.get("id"),
            confidence=score / 100.0,
        )

        # Get artist
        artist_credit = best_match.get("artist-credit", [])
        if artist_credit:
            mb_result.artist = artist_credit[0].get("name") or artist_credit[0].get("artist", {}).get("name")

        # Get release info (album)
        releases = best_match.get("release-list", [])
        if releases:
            release = releases[0]
            mb_result.album = release.get("title")
            mb_result.musicbrainz_release_id = release.get("id")

            # Get year from release date
            date = release.get("date", "")
            if date and len(date) >= 4:
                try:
                    mb_result.year = int(date[:4])
                except ValueError:
                    pass

            # Get track number from medium-list
            media = release.get("medium-list", [])
            if media:
                tracks = media[0].get("track-list", [])
                if tracks:
                    try:
                        mb_result.track_number = int(tracks[0].get("number", 0))
                    except (ValueError, TypeError):
                        pass
                    mb_result.track_total = media[0].get("track-count")

        return mb_result

    except Exception:
        return None


def lookup_by_acoustid(
    fingerprint: str,
    duration: int,
    api_key: str,
) -> MusicBrainzResult | None:
    """Look up track using AcoustID fingerprint.

    This requires an AcoustID API key and the acoustid library.
    """
    try:
        import acoustid

        _rate_limit()

        results = acoustid.lookup(api_key, fingerprint, duration)

        for score, recording_id, title, artist in acoustid.parse_lookup_result(results):
            if score > 0.8:  # High confidence match
                return MusicBrainzResult(
                    artist=artist,
                    title=title,
                    musicbrainz_recording_id=recording_id,
                    confidence=score,
                )

    except Exception:
        pass

    return None


def enrich_metadata(metadata: TrackMetadata, api_key: str | None = None) -> TrackMetadata:
    """Attempt to fill in missing metadata using MusicBrainz.

    Returns a new TrackMetadata with any found information filled in.
    """
    if metadata.is_complete:
        return metadata

    # Try lookup by existing metadata first
    result = lookup_by_metadata(
        artist=metadata.effective_artist,
        album=metadata.album,
        title=metadata.title,
        duration_ms=int(metadata.duration * 1000) if metadata.duration else None,
    )

    if result and result.confidence > 0.8:
        # Fill in missing fields
        if not metadata.artist and result.artist:
            metadata.artist = result.artist
        if not metadata.album and result.album:
            metadata.album = result.album
        if not metadata.title and result.title:
            metadata.title = result.title
        if not metadata.year and result.year:
            metadata.year = result.year
        if not metadata.track_number and result.track_number:
            metadata.track_number = result.track_number

    return metadata


def get_album_art_url(release_id: str) -> str | None:
    """Get cover art URL from Cover Art Archive."""
    if not release_id:
        return None

    _rate_limit()

    try:
        result = musicbrainzngs.get_image_list(release_id)
        images = result.get("images", [])

        # Prefer front cover
        for image in images:
            if image.get("front"):
                return image.get("image")

        # Fall back to any image
        if images:
            return images[0].get("image")

    except Exception:
        pass

    return None


@dataclass
class ArtistLookupResult:
    """Result from a MusicBrainz artist lookup."""

    canonical_name: str
    musicbrainz_id: str
    score: int  # 0-100 match score
    sort_name: str | None = None
    disambiguation: str | None = None
    country: str | None = None


def lookup_artist(artist_name: str, min_score: int = 90) -> ArtistLookupResult | None:
    """Look up canonical artist name from MusicBrainz.

    Args:
        artist_name: The artist name to look up
        min_score: Minimum match score (0-100) to accept

    Returns:
        ArtistLookupResult if found with high confidence, None otherwise
    """
    if not artist_name or not artist_name.strip():
        return None

    _rate_limit()

    try:
        result = musicbrainzngs.search_artists(
            query=f'artist:"{artist_name}"',
            limit=5,
        )

        artists = result.get("artist-list", [])
        if not artists:
            return None

        # Find best match
        for artist in artists:
            score = int(artist.get("ext:score", 0))
            if score >= min_score:
                return ArtistLookupResult(
                    canonical_name=artist.get("name", artist_name),
                    musicbrainz_id=artist.get("id", ""),
                    score=score,
                    sort_name=artist.get("sort-name"),
                    disambiguation=artist.get("disambiguation"),
                    country=artist.get("country"),
                )

        return None

    except Exception:
        return None


def batch_lookup_artists(
    artist_names: list[str],
    min_score: int = 90,
    progress_callback=None,
) -> dict[str, str]:
    """Look up canonical names for multiple artists.

    Args:
        artist_names: List of artist names to look up
        min_score: Minimum match score to accept
        progress_callback: Optional callback(current, total, name)

    Returns:
        Dict mapping original name -> canonical name (only includes found artists)
    """
    import logging
    logger = logging.getLogger("music_organizer")

    results: dict[str, str] = {}
    total = len(artist_names)

    for idx, name in enumerate(artist_names):
        if progress_callback:
            progress_callback(idx + 1, total, name)

        result = lookup_artist(name, min_score)
        if result:
            canonical = result.canonical_name
            if canonical.lower() != name.lower():
                logger.info(f"MusicBrainz: '{name}' -> '{canonical}' (score: {result.score})")
                results[name] = canonical
            elif canonical != name:
                # Same name but different casing
                logger.debug(f"MusicBrainz: '{name}' -> '{canonical}' (case fix)")
                results[name] = canonical

    return results


@dataclass
class ReleaseLookupResult:
    """Result from a MusicBrainz release (album) lookup."""

    title: str
    artist: str
    musicbrainz_id: str
    score: int  # 0-100 match score
    is_compilation: bool = False
    release_type: str | None = None  # "album", "compilation", "soundtrack", etc.
    year: int | None = None


def lookup_release(
    album: str,
    artist: str | None = None,
    min_score: int = 85,
) -> ReleaseLookupResult | None:
    """Look up release info from MusicBrainz to verify if it's a compilation.

    Args:
        album: The album name to look up
        artist: Optional artist name to help narrow the search
        min_score: Minimum match score (0-100) to accept

    Returns:
        ReleaseLookupResult if found with high confidence, None otherwise
    """
    if not album or not album.strip():
        return None

    _rate_limit()

    try:
        # Build search query
        query_parts = [f'release:"{album}"']
        if artist:
            query_parts.append(f'artist:"{artist}"')

        query = " AND ".join(query_parts)

        result = musicbrainzngs.search_releases(
            query=query,
            limit=5,
        )

        releases = result.get("release-list", [])
        if not releases:
            return None

        # Find best match
        for release in releases:
            score = int(release.get("ext:score", 0))
            if score >= min_score:
                # Get artist name
                artist_credit = release.get("artist-credit", [])
                release_artist = ""
                if artist_credit:
                    release_artist = artist_credit[0].get("name") or artist_credit[0].get("artist", {}).get("name", "")

                # Check release group for type info
                release_group = release.get("release-group", {})
                release_type = release_group.get("type", "").lower()
                secondary_types = release_group.get("secondary-type-list", [])

                # Check if it's a compilation
                is_compilation = (
                    release_type == "compilation" or
                    "Compilation" in secondary_types or
                    release_artist.lower() in ("various artists", "various", "v/a")
                )

                # Get year
                date = release.get("date", "")
                year = None
                if date and len(date) >= 4:
                    try:
                        year = int(date[:4])
                    except ValueError:
                        pass

                return ReleaseLookupResult(
                    title=release.get("title", album),
                    artist=release_artist,
                    musicbrainz_id=release.get("id", ""),
                    score=score,
                    is_compilation=is_compilation,
                    release_type=release_type or None,
                    year=year,
                )

        return None

    except Exception:
        return None


def is_compilation_on_musicbrainz(album: str, artist: str | None = None) -> bool | None:
    """Check MusicBrainz to see if an album is a compilation.

    Returns:
        True if confirmed compilation
        False if confirmed NOT a compilation (single artist album)
        None if couldn't determine (lookup failed or low confidence)
    """
    import logging
    logger = logging.getLogger("music_organizer")

    result = lookup_release(album, artist, min_score=80)

    if result:
        logger.debug(
            f"MusicBrainz release lookup: '{album}' by '{artist}' -> "
            f"'{result.title}' by '{result.artist}' "
            f"(type={result.release_type}, compilation={result.is_compilation}, score={result.score})"
        )
        return result.is_compilation

    return None
