# Music Organizer

A retro-styled CLI tool to organize your music library by metadata. Features a funky 1980s stereo visualizer and smart compilation detection.

```
██████████████████████████████████

  ╔╦╗╦ ╦╔═╗╦╔═╗  ╔═╗╦═╗╔═╗╔═╗╔╗╔╦╔═╗╔═╗╦═╗
  ║║║║ ║╚═╗║║    ║ ║╠╦╝║ ╦╠═╣║║║║╔═╝║╣ ╠╦╝
  ╩ ╩╚═╝╚═╝╩╚═╝  ╚═╝╩╚═╚═╝╩ ╩╝╚╝╩╚═╝╚═╝╩╚═

██████████████████████████████████
```

## Features

- **Smart Organization**: Reorganizes files into `Artist/Album (Year)/` structure
- **Metadata Extraction**: Reads tags from MP3, FLAC, M4A, OGG, WAV, and more
- **MusicBrainz Lookup**: Fills in missing metadata from MusicBrainz database
- **Compilation Detection**: Keeps compilation albums together (Various Artists, soundtracks)
- **Discogs Verification**: Optional secondary verification for compilations
- **Artist Normalization**: Merges variations like "DJ Shadow" and "Dj Shadow"
- **Duplicate Detection**: Finds and separates duplicate files by content hash
- **Album Art Management**: Downloads missing artwork from Cover Art Archive
- **Retro Visualizer**: 80s-style bouncing VU meter bars with music trivia
- **Interactive Mode**: Menu-driven interface for non-technical users

## Installation

```bash
# Clone the repo
git clone https://github.com/yourusername/music-organizer.git
cd music-organizer

# Install
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"
```

## Quick Start

### Interactive Mode (Recommended)

Just run without arguments for a friendly menu:

```bash
music-organizer
```

### Command Line

```bash
# Preview what will happen (dry run)
music-organizer organize /path/to/music

# Actually organize files
music-organizer organize /path/to/music --execute

# With the retro visualizer
music-organizer organize /path/to/music -V

# Skip MusicBrainz lookups (faster)
music-organizer organize /path/to/music --no-lookup

# Show file metadata
music-organizer info /path/to/song.mp3

# Scan and show library stats
music-organizer scan /path/to/music
```

## Folder Patterns

Customize how files are organized:

```bash
# Default: Artist/Album (Year)/
music-organizer organize /music -p "{artist}/{album} ({year})"

# By year: Artist/Year - Album/
music-organizer organize /music -p "{artist}/{year} - {album}"

# By genre: Genre/Artist/Album/
music-organizer organize /music -p "{genre}/{artist}/{album}"
```

## Compilation Detection

The tool automatically detects compilation albums:

- **Various Artists albums**: Kept together under `_Compilations/Album (Year)/`
- **Soundtracks**: Organized under `Soundtracks/Album (Year)/`
- **Single-artist "Greatest Hits"**: Stays with the artist (not marked as compilation)

For better accuracy, add a free Discogs API token:

```bash
# Get token at https://www.discogs.com/settings/developers
music-organizer organize /music --discogs-token YOUR_TOKEN

# Or set environment variable
export DISCOGS_TOKEN=your_token
```

## Artist Normalization

Automatically merges artist name variations:

- "DJ Shadow" / "Dj Shadow" / "dj shadow" → "DJ Shadow"
- "The Beatles" / "Beatles" → "The Beatles"
- Punctuation variants merged (e.g., "Harry Connick Jr" / "Harry Connick, Jr.")

## What Happens to Files

| File Type | Destination |
|-----------|-------------|
| Complete metadata | `Artist/Album (Year)/` |
| Compilation albums | `_Compilations/Album (Year)/` |
| Soundtracks | `Soundtracks/Album (Year)/` |
| Missing metadata | `_Unsorted/` |
| Duplicates | `_Duplicates/` |

## Commands

| Command | Description |
|---------|-------------|
| `organize` | Reorganize library by metadata |
| `scan` | Show metadata summary |
| `artwork` | Manage album artwork |
| `info` | Show single file metadata |

## Options

```
--execute, -x       Actually move files (default is dry-run preview)
--visualizer, -V    Show retro 80s stereo visualizer
--pattern, -p       Folder structure pattern
--no-lookup         Skip MusicBrainz lookups
--no-compilations   Disable compilation detection
--no-normalize      Disable artist name normalization
--no-duplicates     Disable duplicate detection
--verbose, -v       Show debug output
--log, -L FILE      Write log to file
```

## Requirements

- Python 3.10+
- mutagen (audio metadata)
- musicbrainzngs (MusicBrainz API)
- rich (terminal UI)
- click (CLI framework)
- python3-discogs-client (optional, for Discogs verification)

## License

MIT
