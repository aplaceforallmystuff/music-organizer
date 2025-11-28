# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Music library organizer that extracts metadata from audio files and reorganizes them into a clean folder structure. Supports MP3, FLAC, M4A, OGG, WAV, and other formats via mutagen.

## Commands

```bash
# Install dependencies
cd ~/music-organizer
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"

# Run CLI commands
music-organizer scan /path/to/music          # Scan and show metadata
music-organizer organize /path/to/music      # Dry-run organization plan
music-organizer organize /path/to/music -x   # Execute organization
music-organizer artwork /path/to/music       # Manage album art
music-organizer info /path/to/file.mp3       # Show single file metadata

# Run tests
pytest
pytest tests/test_metadata.py -v             # Single test file
pytest -k "test_extract"                     # Tests matching pattern

# Linting
ruff check src/
ruff format src/

# Type checking
mypy src/
```

## Architecture

```
src/music_organizer/
├── cli.py              # Click-based CLI with rich output
├── config.py           # Configuration dataclass
├── metadata.py         # Audio metadata extraction (mutagen)
├── musicbrainz_lookup.py # MusicBrainz API for missing metadata
├── discogs_lookup.py   # Discogs API for compilation verification
├── normalization.py    # Artist name normalization and compilation detection
├── album_art.py        # Cover art download/extraction
├── cache.py            # Scan result caching for faster subsequent runs
├── visualizer.py       # Retro 80s stereo visualizer
├── interactive.py      # Interactive menu mode
└── organizer.py        # Core organization logic
```

### Key Classes

- `TrackMetadata` (metadata.py): Dataclass holding extracted metadata with `is_complete` and `missing_fields` properties
- `Config` (config.py): Configuration with folder patterns like `{artist}/{album} ({year})`
- `MusicOrganizer` (organizer.py): Main organizer with `scan()` returning an `OrganizationPlan` and `execute()` to apply it
- `AlbumArtManager` (album_art.py): Handles finding, extracting, and downloading album art

### Data Flow

1. `scan_directory()` → yields `TrackMetadata` for each audio file
2. `MusicOrganizer.scan()` → creates `OrganizationPlan` with `FileOperation` items
3. `MusicOrganizer.execute()` → applies the plan (moves files)

### MusicBrainz Integration

Rate-limited to 1 request/second. Uses `musicbrainzngs` for metadata lookup and Cover Art Archive for album art. AcoustID fingerprinting available with API key.

## Configuration Patterns

Folder pattern placeholders: `{artist}`, `{album}`, `{year}`, `{genre}`
File pattern placeholders: `{track:02d}`, `{title}`, `{artist}`, `{album}`, `{disc}`

Default structure: `Artist/Album (Year)/01 - Title.ext`

## Safety Features

- Dry-run mode by default (`--execute` flag required to move files)
- Hash-based duplicate detection before moving
- Files with missing metadata go to `_Unsorted/` folder
- Associated files (artwork, cue sheets) move with the last audio file from a directory
