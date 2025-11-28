"""Artist name normalization and compilation detection."""

import logging
import re
from collections import Counter, defaultdict
from pathlib import Path

logger = logging.getLogger("music_organizer")

# Common variations that should be normalized
# Format: canonical_name -> [variations]
ARTIST_ALIASES = {
    "AC/DC": ["AC-DC", "ACDC", "Ac/Dc"],
    "R.E.M.": ["REM", "R.E.M", "Rem"],
    "P!nk": ["Pink", "P!NK"],
    "Guns N' Roses": ["Guns N Roses", "Guns 'N' Roses", "GNR", "Guns And Roses"],
    "The Beatles": ["Beatles"],
    "The Rolling Stones": ["Rolling Stones"],
    "The Who": ["Who"],
    '"Weird Al" Yankovic': ["'Weird Al' Yankovic", "Weird Al Yankovic", "Weird Al", "Al Yankovic"],
}

# Words in ALBUM ARTIST field that indicate a compilation album
# These only trigger if the album_artist field contains these values
COMPILATION_ARTIST_INDICATORS = [
    "various artists",
    "various",
    "v.a.",
    "v/a",
    "soundtrack",  # When album artist is "Soundtrack"
]

# Words in album name that STRONGLY suggest compilation (multi-artist)
# These are compilation series that are almost always Various Artists
COMPILATION_SERIES_INDICATORS = [
    "now that's what i call",
    "ministry of sound",
    "cafe del mar",
    "buddha bar",
    "hotel costes",
    "pure moods",
    "bootie",  # Mashup compilations - always multi-artist
]

# Album name patterns that suggest compilation
COMPILATION_ALBUM_PATTERNS = [
    r"^now\s+\d+",  # Now 1, Now 2, etc.
    r"^now that's what i call",
    r"^ministry of sound",
    r"^\d{4} (hits|songs|tracks)",
    r"^top \d+ (hits|songs)",
    r"^a very bootie",  # Bootie mashup series - always multi-artist
    r"bootie.*christmas",  # Bootie Christmas compilations
]

# NOTE: "greatest hits", "best of", "soundtrack", "ost" are NOT here because
# these are often single-artist albums (e.g., "Queen - Greatest Hits")
# We verify these against MusicBrainz instead


def _normalize_for_comparison(name: str) -> str:
    """Normalize a name for fuzzy comparison.

    Strips whitespace, lowercases, removes quotes, and normalizes common variations.
    """
    if not name:
        return ""

    # Lowercase and strip
    normalized = name.lower().strip()

    # Remove all types of quotes (straight and curly)
    # This handles 'Weird Al' vs Weird Al, "Artist" vs Artist, etc.
    normalized = re.sub(r"['\"`'\u2018\u2019\u201c\u201d]", "", normalized)

    # Normalize DJ/Dj/dj -> dj (for comparison only)
    normalized = re.sub(r'\bdj\b', 'dj', normalized, flags=re.IGNORECASE)

    # Normalize MC/Mc/mc -> mc
    normalized = re.sub(r'\bmc\b', 'mc', normalized, flags=re.IGNORECASE)

    # Remove extra whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def _normalize_artist_for_comparison(artist: str) -> str:
    """Normalize an artist name for fuzzy comparison.

    More aggressive than album normalization - also handles:
    - Quote variations ('Weird Al' vs Weird Al)
    - Punctuation variations (Jr vs Jr.)
    - Common separators (& vs and)
    - Feature/collaboration syntax
    """
    if not artist:
        return ""

    normalized = artist.lower().strip()

    # Remove all types of quotes (straight and curly)
    # This handles 'Weird Al' vs Weird Al, "Artist" vs Artist, etc.
    normalized = re.sub(r"['\"`'\u2018\u2019\u201c\u201d]", "", normalized)

    # Remove punctuation that varies between versions
    # "Harry Connick, Jr." vs "Harry Connick Jr" -> "harry connick jr"
    normalized = re.sub(r'[.,;:!?]', '', normalized)

    # Normalize "and" / "&"
    normalized = re.sub(r'\s+&\s+', ' and ', normalized)

    # Normalize featuring syntax
    normalized = re.sub(r'\s+(feat\.?|ft\.?|featuring)\s+', ' feat ', normalized, flags=re.IGNORECASE)

    # Normalize DJ/Dj/dj
    normalized = re.sub(r'\bdj\b', 'dj', normalized, flags=re.IGNORECASE)

    # Normalize MC/Mc/mc
    normalized = re.sub(r'\bmc\b', 'mc', normalized, flags=re.IGNORECASE)

    # Remove extra whitespace
    normalized = ' '.join(normalized.split())

    return normalized


def _extract_primary_artist(artist: str) -> str:
    """Extract the primary artist from a collaboration/featuring string.

    "Elton John & Dua Lipa" -> "elton john"
    "Moby Ft. Jim James" -> "moby"
    "Artist feat. Someone" -> "artist"

    This is used to detect when multiple folder names are actually
    variations of the same primary artist with different collaborators.
    """
    if not artist:
        return ""

    normalized = artist.lower().strip()

    # Remove featuring part: "Artist feat. Someone" -> "Artist"
    # Must come before & handling because "feat" might be abbreviated
    normalized = re.sub(r'\s+(feat\.?|ft\.?|featuring)\s+.*$', '', normalized, flags=re.IGNORECASE)

    # Remove collaboration part: "Artist & Someone" -> "Artist"
    # Only if the & appears to separate artists (not in band names like "Tom Petty & The Heartbreakers")
    # Look for patterns like "Artist1 & Artist2" where both look like names
    if ' & ' in normalized or ' and ' in normalized:
        # Check if this looks like a collaboration vs a band name
        parts = re.split(r'\s+(?:&|and)\s+', normalized)
        if len(parts) >= 2:
            # If second part starts with "the " it's likely a band name, keep it
            if not parts[1].startswith('the '):
                normalized = parts[0]

    # Remove punctuation
    normalized = re.sub(r'[.,;:!?]', '', normalized)

    # Normalize whitespace
    normalized = ' '.join(normalized.split())

    return normalized


class ArtistNormalizer:
    """Normalizes artist names for consistent folder organization."""

    def __init__(self):
        # Build reverse lookup: variation -> canonical
        self._alias_map: dict[str, str] = {}
        for canonical, variations in ARTIST_ALIASES.items():
            self._alias_map[canonical.lower()] = canonical
            for var in variations:
                self._alias_map[var.lower()] = canonical

        # Cache for learned normalizations from the library
        self._learned_names: dict[str, str] = {}  # normalized_key -> preferred form

        # MusicBrainz lookups: original_name -> canonical_name
        self._musicbrainz_names: dict[str, str] = {}

        # Track which original names map to each normalized key (for logging)
        self._name_variants: dict[str, list[str]] = defaultdict(list)

    def normalize(self, artist: str) -> str:
        """Normalize an artist name to a canonical form."""
        if not artist:
            return artist

        # Check MusicBrainz lookups first (highest authority)
        if artist in self._musicbrainz_names:
            return self._musicbrainz_names[artist]

        # Check built-in aliases
        lower = artist.lower()
        if lower in self._alias_map:
            return self._alias_map[lower]

        # Create normalized key for fuzzy matching
        normalized_key = _normalize_for_comparison(artist)

        # Check learned names from library scan using fuzzy key
        if normalized_key in self._learned_names:
            return self._learned_names[normalized_key]

        # Apply standard normalization rules
        normalized = self._apply_rules(artist)

        return normalized

    def _apply_rules(self, artist: str) -> str:
        """Apply standard normalization rules."""
        # Strip extra whitespace
        artist = " ".join(artist.split())

        # Normalize "DJ" variations - always uppercase DJ
        artist = re.sub(r"^Dj\b", "DJ", artist)
        artist = re.sub(r"^dj\b", "DJ", artist, flags=re.IGNORECASE)

        # Normalize "MC" variations
        artist = re.sub(r"^Mc\b", "MC", artist)
        artist = re.sub(r"^mc\b", "MC", artist, flags=re.IGNORECASE)

        # Normalize "The" at the beginning
        if artist.lower().startswith("the "):
            artist = "The " + artist[4:]

        return artist

    def learn_from_library(self, source_dir: Path):
        """Scan existing library to learn preferred artist name forms.

        Groups names by fuzzy match (e.g., "DJ Shadow" and "Dj Shadow" group together)
        and uses the most common form as canonical.
        """
        # Collect all artist folder names
        artist_folders: list[str] = []

        for item in source_dir.iterdir():
            if item.is_dir() and not item.name.startswith(("_", ".")):
                artist_folders.append(item.name)

        # Group by normalized form
        groups: dict[str, Counter] = defaultdict(Counter)

        for name in artist_folders:
            normalized_key = _normalize_for_comparison(name)
            groups[normalized_key][name] += 1
            self._name_variants[normalized_key].append(name)

        # For each group, pick the best canonical form
        for normalized_key, name_counts in groups.items():
            variants = list(name_counts.keys())

            if len(variants) > 1:
                # Multiple variants exist - log this!
                logger.info(f"Found artist name variants: {variants}")

            # Pick canonical form:
            # 1. Prefer names with proper quotes (double over single, quotes over none)
            # 2. Prefer names with proper "DJ" over "Dj"
            # 3. Then prefer most common
            # 4. Then prefer longer (more complete) names

            def score_name(name: str) -> tuple:
                count = name_counts[name]
                has_proper_dj = name.startswith("DJ ") or " DJ " in name
                # Prefer double quotes over single quotes over no quotes
                has_double_quotes = '"' in name
                has_single_quotes = "'" in name and not has_double_quotes
                quote_score = 2 if has_double_quotes else (1 if has_single_quotes else 0)
                length = len(name)
                return (quote_score, has_proper_dj, count, length)

            best_name = max(variants, key=score_name)
            self._learned_names[normalized_key] = best_name

            if len(variants) > 1:
                logger.info(f"  -> Canonical form: '{best_name}'")

    def get_variant_groups(self) -> dict[str, list[str]]:
        """Return groups of artist names that are variants of each other."""
        return {k: v for k, v in self._name_variants.items() if len(v) > 1}

    def learn_from_musicbrainz(self, source_dir: Path, progress_callback=None):
        """Query MusicBrainz for canonical artist names.

        Scans artist folder names and looks them up on MusicBrainz to get
        the official canonical spelling.

        Note: This is rate-limited to 1 request/second by MusicBrainz API limits.
        For a large library this can take a while.
        """
        from .musicbrainz_lookup import batch_lookup_artists, init_musicbrainz

        # Collect unique artist folder names
        artist_names: list[str] = []

        for item in source_dir.iterdir():
            if item.is_dir() and not item.name.startswith(("_", ".")):
                artist_names.append(item.name)

        if not artist_names:
            return

        logger.info(f"Looking up {len(artist_names)} artists on MusicBrainz...")
        logger.info("(This is rate-limited to ~1/second, may take a while)")

        # Initialize MusicBrainz
        init_musicbrainz()

        # Batch lookup
        results = batch_lookup_artists(
            artist_names,
            min_score=90,
            progress_callback=progress_callback,
        )

        self._musicbrainz_names = results

        if results:
            logger.info(f"Found {len(results)} artist name corrections from MusicBrainz")
        else:
            logger.info("No artist name corrections found from MusicBrainz")


class CompilationDetector:
    """Detects compilation albums based on metadata patterns.

    Conservative approach: Only marks albums as compilations when:
    1. Album artist is explicitly "Various Artists" or similar
    2. Album appears under 3+ genuinely different artists in the library
    3. Album matches known compilation series patterns (Bootie, Now That's What I Call, etc.)
    4. Verified as compilation by MusicBrainz and/or Discogs (if lookup enabled)

    Does NOT mark as compilation:
    - Greatest Hits albums by a single artist
    - Best Of albums by a single artist
    - Albums that just happen to have multiple featuring artists
    """

    def __init__(self, verify_with_musicbrainz: bool = False, verify_with_discogs: bool = False):
        self._album_patterns = [re.compile(p, re.IGNORECASE) for p in COMPILATION_ALBUM_PATTERNS]
        self._verify_with_musicbrainz = verify_with_musicbrainz
        self._verify_with_discogs = verify_with_discogs

        # Track which albums appear under multiple artist folders
        # album_name (normalized) -> set of artist folders
        self._album_locations: dict[str, set[str]] = defaultdict(set)

        # Albums confirmed as compilations from folder analysis (3+ distinct artists)
        self._known_compilations: set[str] = set()

        # Cache for database verification results (MusicBrainz + Discogs)
        self._db_verified: dict[str, bool] = {}  # album_key -> is_compilation

    def learn_from_library(self, source_dir: Path):
        """Scan library to find albums that appear under multiple artists.

        An album appearing under 2+ different artist folders is likely a compilation.
        Uses fuzzy artist matching to avoid false positives from punctuation variants
        like "Harry Connick Jr" vs "Harry Connick, Jr."
        """
        logger.info("Scanning for compilation albums (albums under multiple artists)...")

        # Track album -> primary_artist -> [original_artist_names]
        # Use PRIMARY artist (strips featuring/collaboration) to detect:
        # "Elton John & Dua Lipa", "Elton John & Eddie Vedder" -> all "elton john"
        album_to_primary_artists: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        # Also track by full normalized artist for variant detection
        album_to_normalized_artists: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))

        # Scan Artist/Album folder structure
        for artist_dir in source_dir.iterdir():
            if not artist_dir.is_dir() or artist_dir.name.startswith(("_", ".")):
                continue

            artist_name = artist_dir.name
            normalized_artist = _normalize_artist_for_comparison(artist_name)
            primary_artist = _extract_primary_artist(artist_name)

            for album_dir in artist_dir.iterdir():
                if not album_dir.is_dir():
                    continue

                # Normalize album name for comparison
                album_name = album_dir.name
                normalized_album = _normalize_for_comparison(album_name)

                # Also try stripping year suffix like "(2015)"
                normalized_album_no_year = re.sub(r'\s*\(\d{4}\)\s*$', '', normalized_album)

                # Track by PRIMARY artist to catch "Elton John & X" variants
                album_to_primary_artists[normalized_album][primary_artist].append(artist_name)
                album_to_normalized_artists[normalized_album][normalized_artist].append(artist_name)
                self._album_locations[normalized_album].add(artist_name)

                if normalized_album_no_year != normalized_album:
                    album_to_primary_artists[normalized_album_no_year][primary_artist].append(artist_name)
                    album_to_normalized_artists[normalized_album_no_year][normalized_artist].append(artist_name)
                    self._album_locations[normalized_album_no_year].add(artist_name)

        # Albums under 3+ DISTINCT PRIMARY artists might be compilations
        # Using PRIMARY artist count to avoid false positives from:
        # - "Elton John & Dua Lipa", "Elton John & Eddie Vedder" -> same primary artist
        # - "Moby", "Moby Ft. Jim James" -> same primary artist
        for album_key, primary_artists in album_to_primary_artists.items():
            unique_primary_count = len(primary_artists)
            normalized_artists = album_to_normalized_artists.get(album_key, {})
            unique_normalized_count = len(normalized_artists)

            if unique_primary_count >= 3:
                # Get sample of original artist names for logging
                sample_artists = []
                for orig_names in list(primary_artists.values())[:5]:
                    sample_artists.append(orig_names[0])

                # Check if this is likely different albums with the same name
                # vs one true compilation album
                if (self._verify_with_musicbrainz or self._verify_with_discogs) and unique_primary_count <= 10:
                    # Verify with databases - if each artist has their own release
                    # of an album with this name, it's NOT a compilation
                    is_true_compilation = self._verify_compilation_via_databases(
                        album_key, list(primary_artists.keys())[:3]
                    )
                    if is_true_compilation is False:
                        logger.info(f"Album '{album_key}' appears under {unique_primary_count} artists but database lookup shows these are separate albums, NOT a compilation")
                        continue
                    elif is_true_compilation is None:
                        # Couldn't verify - only mark if 5+ primary artists (higher confidence)
                        if unique_primary_count < 5:
                            logger.debug(f"Album '{album_key}' appears under {unique_primary_count} primary artists - skipping (couldn't verify)")
                            continue

                self._known_compilations.add(album_key)
                logger.info(f"Detected compilation by folder structure: '{album_key}' appears under {unique_primary_count} distinct artists: {sample_artists}{'...' if unique_primary_count > 5 else ''}")

            elif unique_primary_count == 1 and unique_normalized_count > 1:
                # All folders map to the same PRIMARY artist but have different names
                # e.g., "Elton John & Dua Lipa", "Elton John & Eddie Vedder" -> NOT a compilation
                all_variants = []
                for orig_names in normalized_artists.values():
                    all_variants.extend(orig_names)
                logger.debug(f"Album '{album_key}' appears under multiple featuring variants of same artist (not a compilation): {list(set(all_variants))[:3]}...")

            elif unique_primary_count == 2:
                # Only 2 primary artists - could be a false positive
                sample_artists = [list(v)[0] for v in primary_artists.values()]
                logger.debug(f"Album '{album_key}' appears under 2 artists (not auto-marking as compilation): {sample_artists}")

            elif len(self._album_locations.get(album_key, set())) >= 2:
                # Album appeared under multiple folders but they normalized to same artist
                all_variants = []
                for orig_names in normalized_artists.values():
                    all_variants.extend(orig_names)
                if len(set(all_variants)) > 1:
                    logger.debug(f"Album '{album_key}' appears under artist name variants (not a compilation): {list(set(all_variants))}")

        logger.info(f"Found {len(self._known_compilations)} compilation albums from folder analysis")

    def _verify_compilation_via_databases(
        self, album_name: str, sample_artists: list[str]
    ) -> bool | None:
        """Verify if an album is truly a compilation using MusicBrainz and/or Discogs.

        Checks if each artist has their own distinct release with this album name.
        If so, these are different albums (not a compilation).
        If databases show one "Various Artists" release, it's a true compilation.

        Returns:
            True if definitely a compilation (Various Artists release found)
            False if NOT a compilation (each artist has their own release)
            None if couldn't determine
        """
        found_distinct_releases = 0
        found_compilation = False

        # Try MusicBrainz first
        if self._verify_with_musicbrainz:
            from .musicbrainz_lookup import lookup_release as mb_lookup

            for artist in sample_artists[:3]:  # Check up to 3 artists
                result = mb_lookup(album_name, artist, min_score=75)
                if result:
                    if result.is_compilation:
                        logger.debug(f"MusicBrainz confirms '{album_name}' is a compilation")
                        found_compilation = True
                        break
                    else:
                        # Found a non-compilation release by this specific artist
                        found_distinct_releases += 1

        # If MusicBrainz didn't find enough info, try Discogs
        if not found_compilation and found_distinct_releases < 2 and self._verify_with_discogs:
            try:
                from .discogs_lookup import lookup_release as discogs_lookup

                for artist in sample_artists[:3]:
                    result = discogs_lookup(album_name, artist)
                    if result:
                        if result.is_compilation:
                            logger.debug(f"Discogs confirms '{album_name}' is a compilation")
                            found_compilation = True
                            break
                        else:
                            found_distinct_releases += 1
            except ImportError:
                pass  # Discogs not available

        if found_compilation:
            return True
        elif found_distinct_releases >= 2:
            # Multiple artists each have their own album with this name
            logger.debug(f"'{album_name}' has {found_distinct_releases} distinct artist releases (not a compilation)")
            return False
        else:
            return None

    def is_compilation(
        self,
        album_artist: str | None,
        artist: str | None,
        album: str | None,
        track_artists: list[str] | None = None,
    ) -> bool:
        """Determine if an album is a compilation.

        Conservative approach - only returns True when confident.

        Args:
            album_artist: The album artist tag
            artist: The track artist tag
            album: The album name
            track_artists: List of artists from all tracks in the album (if available)

        Returns:
            True if this appears to be a compilation album
        """
        # 1. Check album artist for STRONG compilation indicators
        # These are explicit "Various Artists" type values
        if album_artist:
            lower_aa = album_artist.lower().strip()
            for indicator in COMPILATION_ARTIST_INDICATORS:
                if indicator == lower_aa or lower_aa.startswith(indicator):
                    logger.debug(f"Album '{album}' is compilation: album_artist='{album_artist}'")
                    return True

        # 2. Check if album is a known compilation series
        # These are series that are ALWAYS multi-artist
        if album:
            lower_album = album.lower()
            for indicator in COMPILATION_SERIES_INDICATORS:
                if indicator in lower_album:
                    logger.debug(f"Album '{album}' matches compilation series: '{indicator}'")
                    return True

            # Check regex patterns for known compilation formats
            for pattern in self._album_patterns:
                if pattern.search(album):
                    logger.debug(f"Album '{album}' matches compilation pattern")
                    return True

        # 3. Check if we detected this from folder structure (3+ distinct artists)
        if album:
            normalized_album = _normalize_for_comparison(album)
            normalized_album_no_year = re.sub(r'\s*\(\d{4}\)\s*$', '', normalized_album)

            if normalized_album in self._known_compilations or normalized_album_no_year in self._known_compilations:
                logger.debug(f"Album '{album}' is a known compilation (appears under 3+ artists)")
                return True

        # 4. Optional: Verify with databases (MusicBrainz and/or Discogs)
        if (self._verify_with_musicbrainz or self._verify_with_discogs) and album:
            cache_key = _normalize_for_comparison(album)
            if cache_key not in self._db_verified:
                result = None

                # Try MusicBrainz first
                if self._verify_with_musicbrainz:
                    from .musicbrainz_lookup import is_compilation_on_musicbrainz
                    result = is_compilation_on_musicbrainz(album, artist or album_artist)

                # Try Discogs if MusicBrainz didn't determine
                if result is None and self._verify_with_discogs:
                    try:
                        from .discogs_lookup import is_compilation_on_discogs
                        result = is_compilation_on_discogs(album, artist or album_artist)
                    except ImportError:
                        pass  # Discogs not available

                if result is not None:
                    self._db_verified[cache_key] = result

            if cache_key in self._db_verified:
                if self._db_verified[cache_key]:
                    logger.debug(f"Album '{album}' verified as compilation by database lookup")
                    return True
                else:
                    # Database says NOT a compilation - trust it
                    logger.debug(f"Album '{album}' verified as NOT compilation by database lookup")
                    return False

        # 5. Check if many different track artists (6+ suggests true compilation)
        # Higher threshold than before to avoid false positives
        if track_artists:
            unique_artists = set(a.lower().strip() for a in track_artists if a)
            if len(unique_artists) >= 6:
                logger.debug(f"Album '{album}' has {len(unique_artists)} unique track artists")
                return True

        return False

    def is_soundtrack(self, album: str | None, album_artist: str | None = None) -> bool:
        """Check if album is a movie/game soundtrack."""
        if not album:
            return False

        lower = album.lower()
        soundtrack_indicators = ["soundtrack", "ost", "original score", "motion picture"]

        for indicator in soundtrack_indicators:
            if indicator in lower:
                return True

        if album_artist and "soundtrack" in album_artist.lower():
            return True

        return False


def detect_album_artists(source_dir: Path, album_path: Path) -> list[str]:
    """Get all unique artists from tracks in an album folder.

    Useful for detecting compilations based on artist variety.
    """
    from .metadata import extract_metadata

    artists = []
    audio_extensions = (".mp3", ".flac", ".m4a", ".ogg", ".wav", ".opus")

    for file_path in album_path.iterdir():
        if file_path.suffix.lower() in audio_extensions:
            try:
                metadata = extract_metadata(file_path)
                if metadata.artist:
                    artists.append(metadata.artist)
            except Exception:
                pass

    return artists
