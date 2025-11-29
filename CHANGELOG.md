# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2025-11-28

### Added
- Initial release of Music Organizer CLI tool
- **Core organization:**
  - Organize music library by metadata (Artist/Album (Year)/ structure)
  - Extract metadata from MP3, FLAC, M4A, OGG, WAV files
  - Smart compilation detection (Various Artists, soundtracks, etc.)
  - Artist name normalization (merges case/punctuation variants)
  - Duplicate detection by content hash
- **External integrations:**
  - MusicBrainz integration for missing metadata lookup
  - Discogs integration for compilation verification
  - Cover Art Archive for album artwork management
- **Scan caching:**
  - Cache scans to skip unchanged files on subsequent runs
  - File metadata tracking with modification time/size
  - CLI options: `--cache`/`--no-cache`, `--clear-cache`
  - Cache stored in `.music-organizer-cache.json` in music library
- **Artist name handling:**
  - Quote variation normalization ('Weird Al' vs "Weird Al" vs Weird Al)
  - Remove all quote types during comparison
  - Prefer double quotes when selecting canonical form
  - Built-in aliases (e.g., "Weird Al" Yankovic)
- **User interface:**
  - Interactive menu mode for non-technical users
  - Retro 80s stereo visualizer with music trivia
- **Robustness:**
  - Graceful handling of broken symlinks
  - Skip inaccessible directories without crashing
