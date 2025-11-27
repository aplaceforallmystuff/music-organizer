"""Discogs integration for metadata verification and lookup."""

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("music_organizer")

# Rate limiting: Discogs allows 60 requests per minute for authenticated users
# For unauthenticated, it's more restrictive
_last_request_time: float = 0
_MIN_REQUEST_INTERVAL = 1.0  # 1 second between requests to be safe

# Discogs client instance (initialized lazily)
_discogs_client = None
_discogs_init_attempted = False  # Prevent repeated warnings


def _rate_limit():
    """Ensure we don't exceed Discogs rate limits."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def init_discogs(user_token: str | None = None):
    """Initialize Discogs client.

    Args:
        user_token: Discogs personal access token (REQUIRED for API access).
                   Get one at https://www.discogs.com/settings/developers

    Note: Discogs requires authentication for API access. Without a token,
    searches will fail with 401 errors.
    """
    global _discogs_client, _discogs_init_attempted
    _discogs_init_attempted = True  # Mark that we've tried to initialize

    try:
        import discogs_client

        user_agent = "MusicOrganizer/0.1.0 +https://github.com/user/music-organizer"

        if user_token:
            _discogs_client = discogs_client.Client(user_agent, user_token=user_token)
            logger.debug("Initialized Discogs client with user token")
        else:
            # Discogs now requires authentication for API access
            logger.warning(
                "Discogs token not provided. Discogs lookups will be disabled. "
                "Get a free token at https://www.discogs.com/settings/developers"
            )
            _discogs_client = None
            return None

        return _discogs_client

    except ImportError:
        logger.warning("python3-discogs-client not installed, Discogs lookups disabled")
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize Discogs client: {e}")
        return None


def _get_client():
    """Get or initialize the Discogs client."""
    global _discogs_client, _discogs_init_attempted
    if _discogs_client is None and not _discogs_init_attempted:
        _discogs_init_attempted = True
        init_discogs()
    return _discogs_client


@dataclass
class DiscogsReleaseLookupResult:
    """Result from a Discogs release lookup."""

    title: str
    artist: str
    discogs_id: int
    year: int | None = None
    is_compilation: bool = False
    format_type: str | None = None  # "Album", "Compilation", "Single", etc.
    genres: list[str] | None = None
    styles: list[str] | None = None


def lookup_release(
    album: str,
    artist: str | None = None,
    year: int | None = None,
) -> DiscogsReleaseLookupResult | None:
    """Look up release info from Discogs.

    Args:
        album: The album name to look up
        artist: Optional artist name to help narrow the search
        year: Optional year to help narrow the search

    Returns:
        DiscogsReleaseLookupResult if found, None otherwise
    """
    client = _get_client()
    if not client:
        return None

    if not album or not album.strip():
        return None

    _rate_limit()

    try:
        # Build search query
        query = album
        if artist:
            query = f"{artist} {album}"

        results = client.search(query, type="release")

        if not results or results.count == 0:
            return None

        # Find best match - iterate without slicing (discogs-client doesn't support slices)
        checked = 0
        for result in results:
            if checked >= 5:
                break
            checked += 1
            try:
                # Access result data
                result_title = result.title if hasattr(result, "title") else str(result)
                result_id = result.id if hasattr(result, "id") else None

                if not result_id:
                    continue

                # Get full release details
                _rate_limit()
                release = client.release(result_id)

                # Check if this is a MULTI-ARTIST compilation
                # We distinguish between:
                # - Single-artist "Greatest Hits" (Discogs calls this Compilation, but artist is specific)
                # - True Various Artists compilations (multiple artists)
                #
                # We only mark as compilation if it's truly Various Artists
                is_compilation = False
                format_type = None
                is_format_compilation = False

                # Check formats
                if hasattr(release, "formats") and release.formats:
                    for fmt in release.formats:
                        descriptions = fmt.get("descriptions", [])
                        if "Compilation" in descriptions:
                            is_format_compilation = True
                            format_type = "Compilation"
                            break
                        if not format_type and descriptions:
                            format_type = descriptions[0] if descriptions else None

                # Check artist name - only mark as compilation if VARIOUS ARTISTS
                # Single-artist "Greatest Hits" should NOT be marked as compilation
                artist_name = ""
                if hasattr(release, "artists") and release.artists:
                    artist_name = release.artists[0].name
                    if artist_name.lower() in ("various", "various artists"):
                        is_compilation = True
                    # If it's a format compilation but has a specific artist, it's NOT
                    # a Various Artists compilation (e.g., "Queen - Greatest Hits")
                    # So we leave is_compilation = False in that case

                # Get year
                release_year = None
                if hasattr(release, "year") and release.year:
                    try:
                        release_year = int(release.year)
                    except (ValueError, TypeError):
                        pass

                # Get genres and styles
                genres = list(release.genres) if hasattr(release, "genres") and release.genres else None
                styles = list(release.styles) if hasattr(release, "styles") and release.styles else None

                return DiscogsReleaseLookupResult(
                    title=release.title if hasattr(release, "title") else album,
                    artist=artist_name,
                    discogs_id=result_id,
                    year=release_year,
                    is_compilation=is_compilation,
                    format_type=format_type,
                    genres=genres,
                    styles=styles,
                )

            except Exception as e:
                logger.debug(f"Error processing Discogs result: {e}")
                continue

        return None

    except Exception as e:
        logger.debug(f"Discogs search failed: {e}")
        return None


@dataclass
class DiscogsArtistLookupResult:
    """Result from a Discogs artist lookup."""

    name: str
    discogs_id: int
    real_name: str | None = None
    profile: str | None = None


def lookup_artist(artist_name: str) -> DiscogsArtistLookupResult | None:
    """Look up canonical artist name from Discogs.

    Args:
        artist_name: The artist name to look up

    Returns:
        DiscogsArtistLookupResult if found, None otherwise
    """
    client = _get_client()
    if not client:
        return None

    if not artist_name or not artist_name.strip():
        return None

    _rate_limit()

    try:
        results = client.search(artist_name, type="artist")

        if not results or len(results) == 0:
            return None

        # Get first result
        result = results[0]

        return DiscogsArtistLookupResult(
            name=result.name if hasattr(result, "name") else artist_name,
            discogs_id=result.id if hasattr(result, "id") else 0,
            real_name=result.real_name if hasattr(result, "real_name") else None,
            profile=None,  # Would need another API call to get
        )

    except Exception as e:
        logger.debug(f"Discogs artist search failed: {e}")
        return None


def is_compilation_on_discogs(album: str, artist: str | None = None) -> bool | None:
    """Check Discogs to see if an album is a compilation.

    Returns:
        True if confirmed compilation
        False if confirmed NOT a compilation (single artist album)
        None if couldn't determine (lookup failed)
    """
    result = lookup_release(album, artist)

    if result:
        logger.debug(
            f"Discogs release lookup: '{album}' by '{artist}' -> "
            f"'{result.title}' by '{result.artist}' "
            f"(format={result.format_type}, compilation={result.is_compilation})"
        )
        return result.is_compilation

    return None


def verify_release_exists(album: str, artist: str) -> bool:
    """Check if a specific album by a specific artist exists on Discogs.

    This helps distinguish between:
    - Same album name, different artists (e.g., multiple "Unplugged" albums)
    - True compilation albums with various artists

    Returns:
        True if the album exists for this specific artist
        False if not found
    """
    client = _get_client()
    if not client:
        return False

    _rate_limit()

    try:
        # Search with both artist and album
        query = f"{artist} - {album}"
        results = client.search(query, type="release")

        if not results or results.count == 0:
            return False

        # Check if any result matches both artist and album
        artist_lower = artist.lower()
        album_lower = album.lower()

        # Iterate without slicing (discogs-client doesn't support slices)
        checked = 0
        for result in results:
            if checked >= 5:
                break
            checked += 1
            try:
                result_title = result.title.lower() if hasattr(result, "title") else ""

                # Title format is usually "Artist - Album"
                if artist_lower in result_title and album_lower in result_title:
                    return True

                # Also check if we can access artist info
                if hasattr(result, "artists"):
                    _rate_limit()
                    release = client.release(result.id)
                    if hasattr(release, "artists") and release.artists:
                        release_artist = release.artists[0].name.lower()
                        release_title = release.title.lower() if hasattr(release, "title") else ""

                        if (artist_lower in release_artist or release_artist in artist_lower) and \
                           (album_lower in release_title or release_title in album_lower):
                            return True

            except Exception:
                continue

        return False

    except Exception as e:
        logger.debug(f"Discogs verification failed: {e}")
        return False
