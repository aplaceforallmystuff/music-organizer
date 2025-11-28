"""Command-line interface for the music organizer."""

import os
from pathlib import Path

import click


def _load_env_file():
    """Load environment variables from .env file in project directory."""
    # Look for .env in the package's parent directory
    env_locations = [
        Path(__file__).parent.parent.parent / ".env",  # src/music_organizer/../../.env
        Path.cwd() / ".env",  # Current working directory
    ]

    for env_path in env_locations:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        # Only set if not already in environment
                        if key.strip() not in os.environ:
                            os.environ[key.strip()] = value.strip()
            break


# Load .env file on import
_load_env_file()
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.tree import Tree

from .album_art import AlbumArtManager
from .config import Config
from .logging_config import setup_logging
from .metadata import extract_metadata, scan_directory
from .organizer import MusicOrganizer, OrganizationPlan

console = Console()


SCAN_HELP = """
Scan a directory and show metadata for audio files.

Recursively scans for MP3, FLAC, M4A, OGG, WAV files and displays
a summary of metadata completeness plus a sample table.

\b
EXAMPLES
--------
  # Scan current directory
  music-organizer scan

  # Scan your music library
  music-organizer scan /Volumes/Media/Music

  # Show more files in the table
  music-organizer scan /Volumes/Media/Music --limit 50

  # Show just a few files
  music-organizer scan /Volumes/Media/Music -l 5
"""

ORGANIZE_HELP = """
Organize music library by metadata.

Scans audio files, extracts metadata, and reorganizes them into
a clean folder structure. By default runs in DRY-RUN mode (preview only).

\b
FOLDER PATTERN PLACEHOLDERS
---------------------------
  {artist}     - Artist name (or Album Artist if set)
  {album}      - Album name
  {year}       - Release year
  {genre}      - Genre
  {track:02d}  - Track number, zero-padded (01, 02, ...)
  {track}      - Track number (1, 2, ...)
  {title}      - Track title
  {disc}       - Disc number

\b
EXAMPLES
--------
  # Preview organization (dry run) - NO FILES MOVED
  music-organizer organize /Volumes/Media/Music

  # Actually move files (will ask for confirmation)
  music-organizer organize /Volumes/Media/Music --execute

  # Short form of --execute
  music-organizer organize /Volumes/Media/Music -x

  # Organize to a different destination folder
  music-organizer organize /Volumes/Media/Music --dest /Volumes/Media/Music-Organized

  # Custom folder pattern: Artist/Year - Album/
  music-organizer organize /Volumes/Media/Music -p "{artist}/{year} - {album}"

  # Pattern with genre: Genre/Artist/Album (Year)/
  music-organizer organize /Volumes/Media/Music -p "{genre}/{artist}/{album} ({year})"

  # Skip MusicBrainz lookups (faster, but missing metadata goes to _Unsorted)
  music-organizer organize /Volumes/Media/Music --no-lookup

  # Skip duplicate detection
  music-organizer organize /Volumes/Media/Music --no-duplicates

  # Combine options: custom pattern, no lookups, execute
  music-organizer organize /Volumes/Media/Music -p "{artist}/{album}" --no-lookup -x

\b
COMPILATION & NORMALIZATION
---------------------------
  # Disable compilation detection (keeps "Various Artists" albums split by track artist)
  music-organizer organize /Volumes/Media/Music --no-compilations

  # Use custom folder for compilations (default: _Compilations)
  music-organizer organize /Volumes/Media/Music --compilation-folder "Various Artists"

  # Disable artist name normalization (won't merge "Dj Shadow" and "DJ Shadow")
  music-organizer organize /Volumes/Media/Music --no-normalize

\b
WHAT HAPPENS TO FILES
---------------------
  - Complete metadata    -> Organized to pattern (e.g., Artist/Album (Year)/)
  - Compilation albums   -> _Compilations/Album (Year)/ (keeps tracks together)
  - Soundtracks          -> Soundtracks/Album (Year)/
  - Missing metadata     -> _Unsorted/ folder (or looked up on MusicBrainz)
  - Duplicate files      -> _Duplicates/ folder
  - Associated files     -> Moved with album (cover.jpg, .cue, .log, etc.)

\b
ARTIST NORMALIZATION
--------------------
  By default, learns preferred artist name spellings from your existing library
  and normalizes case variations:
    - "Dj Shadow" and "DJ Shadow" -> "DJ Shadow" (most common form)
    - "the beatles" -> "The Beatles"
    - "Harry Connick Jr" and "Harry Connick, Jr." -> same artist (punctuation normalized)

  Optional: --mb-artists flag queries MusicBrainz for canonical artist names.
  This is SLOW (~1 artist/second due to API rate limits) but gives authoritative
  spellings from the MusicBrainz database.

\b
DISCOGS INTEGRATION
-------------------
  For better compilation detection, you can add a Discogs API token:
  - Get a free token at https://www.discogs.com/settings/developers
  - Use: music-organizer organize /path --discogs-token YOUR_TOKEN
  - Or set DISCOGS_TOKEN environment variable

\b
SCAN CACHING
------------
  By default, scan results are cached to speed up subsequent runs.
  Only files that have changed (different modification time or size)
  are re-scanned. The cache is stored in .music-organizer-cache.json
  in the source directory.

  # Disable caching (always scan all files)
  music-organizer organize /path --no-cache

  # Clear cache before running (force full rescan)
  music-organizer organize /path --clear-cache
"""

ARTWORK_HELP = """
Manage album artwork - find, download, and standardize.

Scans album folders for cover art. Can extract embedded art from
audio files or download from Cover Art Archive (MusicBrainz).

\b
EXAMPLES
--------
  # Scan and download missing artwork
  music-organizer artwork /Volumes/Media/Music

  # Just find and standardize existing art (no downloads)
  music-organizer artwork /Volumes/Media/Music --no-download

  # Limit image size to 500px (smaller files)
  music-organizer artwork /Volumes/Media/Music --max-size 500

  # High quality art (up to 1500px)
  music-organizer artwork /Volumes/Media/Music --max-size 1500

\b
WHAT IT DOES
------------
  1. Finds existing cover.jpg, folder.jpg, etc.
  2. Extracts embedded art from audio files if no file found
  3. Downloads from Cover Art Archive if --download enabled
  4. Standardizes filename to cover.jpg
  5. Resizes if larger than --max-size
"""

INFO_HELP = """
Show detailed metadata for a single audio file.

Displays all available metadata tags, audio quality info,
and identifies any missing required fields.

\b
EXAMPLES
--------
  # Show info for a file
  music-organizer info "/Volumes/Media/Music/Pink Floyd/Wish You Were Here/01 Shine On You Crazy Diamond.flac"

  # Relative path
  music-organizer info "./song.mp3"

\b
FIELDS SHOWN
------------
  - Artist, Album Artist, Album, Title
  - Track number, Disc number
  - Year, Genre
  - Duration, Bitrate, Sample Rate
  - Format (MP3, FLAC, etc.)
  - Whether album art is embedded
"""


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0")
@click.pass_context
def main(ctx):
    """
    Music library organizer - clean up and organize your music collection.

    Run without arguments for interactive menu, or use commands directly.

    \b
    QUICK START
    -----------
      1. Interactive mode (recommended):
         music-organizer

      2. Preview organization (dry run):
         music-organizer organize /path/to/music

      3. Actually organize (moves files):
         music-organizer organize /path/to/music --execute

    \b
    COMMANDS
    --------
      scan      - Show metadata summary for audio files
      organize  - Reorganize files by metadata (dry-run by default)
      artwork   - Find, download, and standardize album art
      info      - Show metadata for a single file

    Use 'music-organizer COMMAND --help' for detailed examples.
    """
    # If no command specified, run interactive mode
    if ctx.invoked_subcommand is None:
        from .interactive import run_interactive
        run_interactive()


@main.command(help=SCAN_HELP)
@click.argument("directory", type=click.Path(exists=True, path_type=Path), default=".")
@click.option(
    "--limit", "-l",
    default=20,
    show_default=True,
    help="Number of files to show in the sample table."
)
def scan(directory: Path, limit: int):
    """Scan a directory and show metadata for audio files."""
    console.print(f"\n[bold]Scanning:[/bold] {directory}\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("Scanning for audio files...", total=None)
        tracks = scan_directory(directory)

    if not tracks:
        console.print("[yellow]No audio files found.[/yellow]")
        return

    # Summary statistics
    complete = sum(1 for t in tracks if t.is_complete)
    with_art = sum(1 for t in tracks if t.has_album_art)

    console.print(f"Found [bold]{len(tracks)}[/bold] audio files")
    console.print(f"  Complete metadata: {complete} ({100*complete//len(tracks)}%)")
    console.print(f"  With album art: {with_art} ({100*with_art//len(tracks)}%)")
    console.print()

    # Show sample of tracks
    table = Table(title=f"Sample tracks (showing {min(limit, len(tracks))} of {len(tracks)})")
    table.add_column("Artist", style="cyan", no_wrap=True)
    table.add_column("Album", style="green")
    table.add_column("Title", style="white")
    table.add_column("Year", style="yellow")
    table.add_column("Art", justify="center")
    table.add_column("Status", justify="center")

    for track in tracks[:limit]:
        status = "[green]✓[/green]" if track.is_complete else f"[red]Missing: {', '.join(track.missing_fields)}[/red]"
        art = "[green]✓[/green]" if track.has_album_art else "[dim]-[/dim]"

        table.add_row(
            track.effective_artist or "[dim]Unknown[/dim]",
            track.album or "[dim]Unknown[/dim]",
            track.title or "[dim]Unknown[/dim]",
            str(track.year) if track.year else "[dim]-[/dim]",
            art,
            status,
        )

    console.print(table)


@main.command(help=ORGANIZE_HELP)
@click.argument("directory", type=click.Path(exists=True, path_type=Path), default=".")
@click.option(
    "--dest", "-d",
    type=click.Path(path_type=Path),
    help="Destination directory. Default: organize in place."
)
@click.option(
    "--pattern", "-p",
    default="{artist}/{album} ({year})",
    show_default=True,
    help="Folder structure pattern using placeholders."
)
@click.option(
    "--lookup/--no-lookup",
    default=True,
    show_default=True,
    help="Look up missing metadata on MusicBrainz."
)
@click.option(
    "--duplicates/--no-duplicates",
    default=True,
    show_default=True,
    help="Detect and separate duplicate files."
)
@click.option(
    "--compilations/--no-compilations",
    default=True,
    show_default=True,
    help="Detect compilation albums and keep tracks together."
)
@click.option(
    "--compilation-folder",
    default="_Compilations",
    show_default=True,
    help="Folder name for compilation albums."
)
@click.option(
    "--normalize/--no-normalize",
    default=True,
    show_default=True,
    help="Normalize artist names (merge case variations like 'Dj Shadow' and 'DJ Shadow')."
)
@click.option(
    "--mb-artists",
    is_flag=True,
    help="Look up canonical artist names on MusicBrainz. SLOW: ~1 artist/second due to API rate limits."
)
@click.option(
    "--discogs-token",
    envvar="DISCOGS_TOKEN",
    help="Discogs API token for release verification. Get one at https://www.discogs.com/settings/developers"
)
@click.option(
    "--execute", "-x",
    is_flag=True,
    help="Actually move files. Without this flag, only shows a preview."
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Show detailed debug output in terminal."
)
@click.option(
    "--log", "-L",
    type=click.Path(path_type=Path),
    help="Write detailed log to file (e.g., --log organize.log)."
)
@click.option(
    "--visualizer", "-V",
    is_flag=True,
    help="Show retro 80s stereo visualizer during scanning."
)
@click.option(
    "--cache/--no-cache",
    default=True,
    show_default=True,
    help="Cache scan results to skip unchanged files on subsequent runs."
)
@click.option(
    "--clear-cache",
    is_flag=True,
    help="Clear the scan cache before running (forces full rescan)."
)
def organize(
    directory: Path,
    dest: Path | None,
    pattern: str,
    lookup: bool,
    duplicates: bool,
    compilations: bool,
    compilation_folder: str,
    normalize: bool,
    mb_artists: bool,
    discogs_token: str | None,
    execute: bool,
    verbose: bool,
    log: Path | None,
    visualizer: bool,
    cache: bool,
    clear_cache: bool,
):
    """Organize music library by metadata."""
    # Setup logging
    setup_logging(verbose=verbose, log_file=log)
    if log:
        console.print(f"[dim]Logging to: {log}[/dim]\n")

    # Handle cache clearing
    if clear_cache:
        from .cache import CACHE_FILENAME
        cache_file = directory / CACHE_FILENAME
        if cache_file.exists():
            cache_file.unlink()
            console.print(f"[yellow]Cleared scan cache[/yellow]\n")

    config = Config(
        source_dir=directory,
        dest_dir=dest,
        folder_pattern=pattern,
        missing_metadata_action="lookup" if lookup else "unsorted",
        detect_duplicates=duplicates,
        detect_compilations=compilations,
        compilation_folder=compilation_folder,
        normalize_artists=normalize,
        musicbrainz_artist_lookup=mb_artists,
        discogs_enabled=bool(discogs_token),
        discogs_token=discogs_token,
        dry_run=not execute,
        use_cache=cache,
    )

    discogs_status = 'Yes' if discogs_token else '[dim]No (provide --discogs-token for extra verification)[/dim]'
    cache_status = '[green]Yes (skips unchanged files)[/green]' if cache else '[dim]No[/dim]'
    console.print(Panel.fit(
        f"[bold]Music Library Organizer[/bold]\n\n"
        f"Source: {config.source_dir}\n"
        f"Destination: {config.dest_dir or 'In-place'}\n"
        f"Pattern: {config.folder_pattern}\n"
        f"MusicBrainz lookup: {'Yes' if lookup else 'No'}\n"
        f"Discogs verification: {discogs_status}\n"
        f"Duplicate detection: {'Yes' if duplicates else 'No'}\n"
        f"Compilation detection: {'Yes' if compilations else 'No'}\n"
        f"Artist normalization: {'Yes' if normalize else 'No'}\n"
        f"Scan cache: {cache_status}\n"
        f"Mode: {'[red bold]EXECUTE[/red bold]' if execute else '[green]DRY RUN (preview only)[/green]'}",
        title="Configuration"
    ))

    if visualizer:
        # Start visualizer BEFORE creating organizer (init can be slow)
        from .visualizer import StereoVisualizer

        viz = StereoVisualizer(num_bars=20, max_height=8, console=console)
        live = viz.start()

        try:
            # Show status during initialization
            viz.set_status("Learning artist names...")
            organizer = MusicOrganizer(config)

            # Now scan with progress
            def update_progress(current, total, path):
                viz.update(current, total, path.name)

            plan = organizer.scan(progress_callback=update_progress)
        finally:
            viz.stop(live)
    else:
        # Standard mode - create organizer first
        organizer = MusicOrganizer(config)

        # Scan and create plan
        console.print("\n[bold]Scanning library...[/bold]\n")

        # Standard progress bar
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
        ) as progress:
            task = progress.add_task("Scanning...", total=None)

            def update_progress(current, total, path):
                progress.update(task, total=total, completed=current, description=f"Scanning: {path.name}")

            plan = organizer.scan(progress_callback=update_progress)

    # Show plan summary
    _show_plan_summary(plan, config)

    if not execute:
        console.print("\n[yellow]This is a dry run. No files were moved.[/yellow]")
        console.print("[yellow]Run with --execute (or -x) to actually move files.[/yellow]")
        return

    # Confirm before executing
    if not click.confirm("\nProceed with moving files?"):
        console.print("[yellow]Aborted.[/yellow]")
        return

    # Execute the plan
    console.print("\n[bold]Moving files...[/bold]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Moving...", total=plan.files_to_move)

        def update_progress(current, total, path):
            progress.update(task, completed=current, description=f"Moving: {path.name}")

        successful, failed = organizer.execute(plan, progress_callback=update_progress)

    console.print(f"\n[green]Successfully moved {successful} files[/green]")
    if failed:
        console.print(f"[red]Failed to move {failed} files[/red]")


def _show_plan_summary(plan: OrganizationPlan, config: Config):
    """Display a summary of the organization plan."""
    console.print("\n[bold]Plan Summary:[/bold]\n")

    stats_table = Table(show_header=False, box=None)
    stats_table.add_column("Label", style="bold")
    stats_table.add_column("Value", justify="right")

    stats_table.add_row("Files to move:", str(plan.files_to_move))
    stats_table.add_row("Files to skip:", str(plan.files_to_skip))
    stats_table.add_row("Duplicates found:", str(len(plan.duplicates)))
    stats_table.add_row("Unsorted (missing metadata):", str(len(plan.unsorted)))
    stats_table.add_row("Errors:", str(len(plan.errors)))

    console.print(stats_table)

    # Show sample of moves
    moves = [op for op in plan.operations if op.operation == "move"][:10]
    if moves:
        console.print("\n[bold]Sample moves:[/bold]\n")

        tree = Tree("[bold]Planned moves[/bold]")
        for op in moves:
            rel_source = op.source.relative_to(config.source_dir)
            dest_base = config.dest_dir or config.source_dir
            rel_dest = op.destination.relative_to(dest_base)

            branch = tree.add(f"[cyan]{rel_source}[/cyan]")
            branch.add(f"[green]→ {rel_dest}[/green]")
            if op.reason:
                branch.add(f"[dim]({op.reason})[/dim]")

        console.print(tree)

    # Show duplicates
    if plan.duplicates:
        console.print(f"\n[bold]Duplicates found: {len(plan.duplicates)}[/bold]\n")
        for original, duplicate in plan.duplicates[:5]:
            console.print(f"  [dim]{duplicate.name}[/dim] duplicates [cyan]{original.name}[/cyan]")
        if len(plan.duplicates) > 5:
            console.print(f"  [dim]...and {len(plan.duplicates) - 5} more[/dim]")

    # Show errors
    if plan.errors:
        console.print(f"\n[red bold]Errors: {len(plan.errors)}[/red bold]\n")
        for path, error in plan.errors[:5]:
            console.print(f"  [red]{path.name}:[/red] {error}")


@main.command(help=ARTWORK_HELP)
@click.argument("directory", type=click.Path(exists=True, path_type=Path), default=".")
@click.option(
    "--download/--no-download",
    default=True,
    show_default=True,
    help="Download missing album art from Cover Art Archive."
)
@click.option(
    "--max-size",
    default=1000,
    show_default=True,
    help="Maximum image dimension in pixels. Larger images are resized."
)
def artwork(directory: Path, download: bool, max_size: int):
    """Manage album artwork - find, download, and standardize."""
    console.print(f"\n[bold]Album Art Manager[/bold]\n")
    console.print(f"Directory: {directory}")
    console.print(f"Download missing: {'Yes' if download else 'No'}")
    console.print(f"Max size: {max_size}px")
    console.print()

    manager = AlbumArtManager(
        download_missing=download,
        max_size=max_size,
    )

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
    ) as progress:
        task = progress.add_task("Processing albums...", total=None)

        def update_progress(current, total, path):
            progress.update(task, total=total, completed=current, description=f"Processing: {path.name}")

        stats = manager.scan_library(directory, progress_callback=update_progress)

    # Show results
    table = Table(title="Album Art Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")

    table.add_row("Total albums", str(stats["total_albums"]))
    table.add_row("With album art", f"[green]{stats['with_art']}[/green]")
    table.add_row("Art added (extracted/downloaded)", str(stats["art_added"]))
    table.add_row("Art downloaded", str(stats["art_downloaded"]))
    table.add_row("Missing art", f"[yellow]{stats['missing_art']}[/yellow]" if stats["missing_art"] else "0")

    console.print(table)


@main.command(help=INFO_HELP)
@click.argument("file", type=click.Path(exists=True, path_type=Path))
def info(file: Path):
    """Show detailed metadata for a single audio file."""
    if not file.is_file():
        console.print("[red]Error: Not a file[/red]")
        return

    metadata = extract_metadata(file)

    console.print(Panel.fit(
        f"[bold]{file.name}[/bold]",
        title="File Info"
    ))

    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold cyan")
    table.add_column("Value")

    fields = [
        ("Artist", metadata.artist),
        ("Album Artist", metadata.album_artist),
        ("Album", metadata.album),
        ("Title", metadata.title),
        ("Track", f"{metadata.track_number or '?'}/{metadata.track_total or '?'}"),
        ("Disc", f"{metadata.disc_number or '?'}/{metadata.disc_total or '?'}"),
        ("Year", metadata.year),
        ("Genre", metadata.genre),
        ("Duration", f"{int(metadata.duration // 60)}:{int(metadata.duration % 60):02d}" if metadata.duration else None),
        ("Bitrate", f"{metadata.bitrate} kbps" if metadata.bitrate else None),
        ("Sample Rate", f"{metadata.sample_rate} Hz" if metadata.sample_rate else None),
        ("Format", metadata.format),
        ("Album Art", "Yes" if metadata.has_album_art else "No"),
    ]

    for field, value in fields:
        if value is not None:
            table.add_row(field, str(value))
        else:
            table.add_row(field, "[dim]Not set[/dim]")

    console.print(table)

    if metadata.missing_fields:
        console.print(f"\n[yellow]Missing fields: {', '.join(metadata.missing_fields)}[/yellow]")


if __name__ == "__main__":
    main()
