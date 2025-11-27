"""Interactive menu system for the music organizer."""

from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich.text import Text


console = Console()


def show_banner():
    """Display the retro-style banner."""
    banner = """
[bold red]██[/bold red][bold yellow]██[/bold yellow][bold green]██[/bold green][bold cyan]██[/bold cyan][bold blue]██[/bold blue][bold magenta]██[/bold magenta][bold red]██[/bold red][bold yellow]██[/bold yellow][bold green]██[/bold green][bold cyan]██[/bold cyan][bold blue]██[/bold blue][bold magenta]██[/bold magenta][bold red]██[/bold red][bold yellow]██[/bold yellow][bold green]██[/bold green][bold cyan]██[/bold cyan]

[bold white]  ╔╦╗╦ ╦╔═╗╦╔═╗  ╔═╗╦═╗╔═╗╔═╗╔╗╔╦╔═╗╔═╗╦═╗  [/bold white]
[bold white]  ║║║║ ║╚═╗║║    ║ ║╠╦╝║ ╦╠═╣║║║║╔═╝║╣ ╠╦╝  [/bold white]
[bold white]  ╩ ╩╚═╝╚═╝╩╚═╝  ╚═╝╩╚═╚═╝╩ ╩╝╚╝╩╚═╝╚═╝╩╚═  [/bold white]

[bold red]██[/bold red][bold yellow]██[/bold yellow][bold green]██[/bold green][bold cyan]██[/bold cyan][bold blue]██[/bold blue][bold magenta]██[/bold magenta][bold red]██[/bold red][bold yellow]██[/bold yellow][bold green]██[/bold green][bold cyan]██[/bold cyan][bold blue]██[/bold blue][bold magenta]██[/bold magenta][bold red]██[/bold red][bold yellow]██[/bold yellow][bold green]██[/bold green][bold cyan]██[/bold cyan]
"""
    console.print(banner)
    console.print("[dim]Organize your music library like it's 1985[/dim]\n")


def show_main_menu() -> str:
    """Show main menu and return user's choice."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold cyan", width=4)
    table.add_column("Option", style="white")

    table.add_row("[1]", "Scan library - Preview what will happen")
    table.add_row("[2]", "Organize library - Move files to new structure")
    table.add_row("[3]", "Manage album artwork")
    table.add_row("[4]", "Show file info")
    table.add_row("[5]", "Settings")
    table.add_row("[Q]", "Quit")

    console.print(Panel(table, title="[bold]Main Menu[/bold]", border_style="cyan"))

    choice = Prompt.ask(
        "\n[bold cyan]Select option[/bold cyan]",
        choices=["1", "2", "3", "4", "5", "q", "Q"],
        default="1"
    )
    return choice.lower()


def get_directory() -> Path:
    """Prompt user for music directory."""
    default_paths = [
        Path("/Volumes/Media/Music"),
        Path.home() / "Music",
        Path.cwd(),
    ]

    # Find first existing path
    default = None
    for p in default_paths:
        if p.exists():
            default = str(p)
            break

    console.print("\n[bold]Music Library Location[/bold]")

    while True:
        path_str = Prompt.ask(
            "Enter path to your music library",
            default=default
        )
        path = Path(path_str).expanduser()

        if path.exists() and path.is_dir():
            return path
        else:
            console.print(f"[red]Directory not found: {path}[/red]")


def get_organize_options() -> dict:
    """Interactive options for organizing."""
    options = {}

    console.print("\n[bold]Organization Options[/bold]\n")

    # Folder pattern
    patterns = [
        ("{artist}/{album} ({year})", "Artist/Album (Year)"),
        ("{artist}/{year} - {album}", "Artist/Year - Album"),
        ("{genre}/{artist}/{album}", "Genre/Artist/Album"),
        ("{artist}/{album}", "Artist/Album (no year)"),
    ]

    console.print("[bold cyan]Folder Structure:[/bold cyan]")
    for i, (pattern, desc) in enumerate(patterns, 1):
        console.print(f"  [{i}] {desc}")
    console.print(f"  [5] Custom pattern")

    pattern_choice = Prompt.ask("Select pattern", choices=["1", "2", "3", "4", "5"], default="1")

    if pattern_choice == "5":
        console.print("\n[dim]Available placeholders: {artist}, {album}, {year}, {genre}[/dim]")
        options["pattern"] = Prompt.ask("Enter custom pattern", default="{artist}/{album} ({year})")
    else:
        options["pattern"] = patterns[int(pattern_choice) - 1][0]

    console.print()

    # Quick settings
    options["lookup"] = Confirm.ask(
        "Look up missing metadata on MusicBrainz?",
        default=True
    )

    options["compilations"] = Confirm.ask(
        "Detect compilation albums and keep tracks together?",
        default=True
    )

    options["duplicates"] = Confirm.ask(
        "Detect and separate duplicate files?",
        default=True
    )

    options["normalize"] = Confirm.ask(
        "Normalize artist names (merge variations like 'Dj Shadow' / 'DJ Shadow')?",
        default=True
    )

    # Visualizer
    console.print()
    options["visualizer"] = Confirm.ask(
        "[bold yellow]Show retro 80s visualizer during scan?[/bold yellow]",
        default=True
    )

    # Execute or dry run
    console.print()
    console.print("[bold yellow]WARNING:[/bold yellow] This will move files in your library!")
    options["execute"] = Confirm.ask(
        "Actually move files? (No = preview only)",
        default=False
    )

    return options


def get_artwork_options() -> dict:
    """Interactive options for artwork management."""
    options = {}

    console.print("\n[bold]Album Artwork Options[/bold]\n")

    options["download"] = Confirm.ask(
        "Download missing album art from Cover Art Archive?",
        default=True
    )

    sizes = [
        ("500", "Small (500px)"),
        ("1000", "Medium (1000px) - Default"),
        ("1500", "Large (1500px)"),
    ]

    console.print("\n[bold cyan]Maximum image size:[/bold cyan]")
    for i, (size, desc) in enumerate(sizes, 1):
        console.print(f"  [{i}] {desc}")

    size_choice = Prompt.ask("Select size", choices=["1", "2", "3"], default="2")
    options["max_size"] = int(sizes[int(size_choice) - 1][0])

    return options


def show_settings_menu():
    """Show and manage settings."""
    import os

    console.print("\n[bold]Current Settings[/bold]\n")

    table = Table(show_header=True, box=None)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="white")
    table.add_column("Status", style="green")

    # Check Discogs token
    discogs_token = os.environ.get("DISCOGS_TOKEN")
    if discogs_token:
        token_display = discogs_token[:8] + "..." + discogs_token[-4:]
        table.add_row("Discogs API Token", token_display, "[green]Configured[/green]")
    else:
        table.add_row("Discogs API Token", "Not set", "[yellow]Optional[/yellow]")

    console.print(table)

    console.print("\n[dim]Discogs token enables extra compilation verification.[/dim]")
    console.print("[dim]Get one free at: https://www.discogs.com/settings/developers[/dim]")

    if not discogs_token:
        if Confirm.ask("\nWould you like to set a Discogs token now?", default=False):
            token = Prompt.ask("Enter your Discogs token")
            if token:
                # Write to .env file
                env_path = Path(__file__).parent.parent.parent / ".env"
                with open(env_path, "a") as f:
                    f.write(f"\nDISCOGS_TOKEN={token}\n")
                os.environ["DISCOGS_TOKEN"] = token
                console.print("[green]Token saved to .env file![/green]")


def run_interactive():
    """Run the interactive menu system."""
    show_banner()

    while True:
        choice = show_main_menu()

        if choice == "q":
            console.print("\n[bold cyan]Thanks for using Music Organizer![/bold cyan]")
            console.print("[dim]Keep the music playing! 🎵[/dim]\n")
            break

        elif choice == "1":
            # Scan (preview)
            directory = get_directory()
            options = get_organize_options()
            options["execute"] = False  # Force preview

            # Import and run
            from .cli import organize as run_organize
            from click.testing import CliRunner

            # Build args
            args = [str(directory)]
            args.extend(["--pattern", options["pattern"]])
            if not options["lookup"]:
                args.append("--no-lookup")
            if not options["compilations"]:
                args.append("--no-compilations")
            if not options["duplicates"]:
                args.append("--no-duplicates")
            if not options["normalize"]:
                args.append("--no-normalize")
            if options["visualizer"]:
                args.append("--visualizer")

            # Run via click
            from .cli import main
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(main, ["organize"] + args, catch_exceptions=False)
            console.print(result.output)

            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "2":
            # Organize (with option to execute)
            directory = get_directory()
            options = get_organize_options()

            # Build args
            args = [str(directory)]
            args.extend(["--pattern", options["pattern"]])
            if not options["lookup"]:
                args.append("--no-lookup")
            if not options["compilations"]:
                args.append("--no-compilations")
            if not options["duplicates"]:
                args.append("--no-duplicates")
            if not options["normalize"]:
                args.append("--no-normalize")
            if options["visualizer"]:
                args.append("--visualizer")
            if options["execute"]:
                args.append("--execute")

            from .cli import main
            from click.testing import CliRunner
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(main, ["organize"] + args, catch_exceptions=False)
            console.print(result.output)

            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "3":
            # Artwork
            directory = get_directory()
            options = get_artwork_options()

            args = [str(directory)]
            args.extend(["--max-size", str(options["max_size"])])
            if not options["download"]:
                args.append("--no-download")

            from .cli import main
            from click.testing import CliRunner
            runner = CliRunner(mix_stderr=False)
            result = runner.invoke(main, ["artwork"] + args, catch_exceptions=False)
            console.print(result.output)

            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "4":
            # File info
            file_path = Prompt.ask("Enter path to audio file")
            path = Path(file_path).expanduser()

            if path.exists() and path.is_file():
                from .cli import main
                from click.testing import CliRunner
                runner = CliRunner(mix_stderr=False)
                result = runner.invoke(main, ["info", str(path)], catch_exceptions=False)
                console.print(result.output)
            else:
                console.print(f"[red]File not found: {path}[/red]")

            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        elif choice == "5":
            # Settings
            show_settings_menu()
            Prompt.ask("\n[dim]Press Enter to continue[/dim]")

        console.clear()
        show_banner()
