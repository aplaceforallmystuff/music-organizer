"""Retro 1980s stereo visualizer for progress display."""

import random
import time
from threading import Thread, Event
from rich.console import Console, Group
from rich.live import Live
from rich.text import Text
from rich.panel import Panel


# Fun music trivia to display while waiting
MUSIC_TRIVIA = [
    "The first music video played on MTV was 'Video Killed the Radio Star' by The Buggles (1981)",
    "A 'jiffy' is an actual unit of time: 1/100th of a second, used in audio timing",
    "The longest officially released song is 'The Rise and Fall of Bossanova' at 13 hours, 23 minutes",
    "Vinyl records spin at 33⅓ RPM because it divides evenly into 60 seconds",
    "The Beatles used the word 'love' 613 times in their songs",
    "The first song played on Armed Forces Radio during Desert Storm was 'Rock the Casbah'",
    "Freddie Mercury's vocal range spanned four octaves",
    "The 'Wilhelm Scream' has been used in over 400 films and TV shows since 1951",
    "The harmonica is the world's best-selling music instrument",
    "Finland has more heavy metal bands per capita than any other country",
    "The shortest #1 hit is 'Stay' by Maurice Williams at 1 minute 36 seconds",
    "Prince played 27 instruments on his debut album",
    "The first commercial CD pressed in the USA was Bruce Springsteen's 'Born in the U.S.A.'",
    "Led Zeppelin's 'Stairway to Heaven' has never been released as a single",
    "Michael Jackson's 'Thriller' album spent 37 weeks at #1",
    "The dot on top of the letter 'i' is called a 'tittle'... wait, that's not music",
    "Jimi Hendrix, Janis Joplin, Jim Morrison, and Kurt Cobain all died at 27",
    "The 'brown note' is a theoretical frequency that causes involuntary bowel movements",
    "The vocoder, used in electronic music, was invented in 1928",
    "A grand piano has 230 strings under approximately 30 tons of tension",
    "Rapper's Delight (1979) was the first hip-hop single to reach the Top 40",
    "The loudest animal on Earth is the sperm whale at 230 decibels",
    "The first iPod could hold 1,000 songs. Today's phones hold 100,000+",
    "The longest guitar solo in a hit song is Free Bird at over 4 minutes",
    "Mozart composed his first symphony at age 8",
    "Adele's album '21' is the best-selling album of the 21st century",
    "The first music was probably made by slapping body parts together",
    "A CD can hold 74 minutes of audio - enough for Beethoven's 9th Symphony",
    "The bass guitar was invented in 1951 by Leo Fender",
    "ABBA turned down $1 billion to reunite in 2000",
    "The original 'Happy Birthday' song is still under copyright until 2030",
    "Spotify has over 100 million tracks in its library",
    "The world's largest music collection has over 3 million albums",
    "Phil Collins is one of three artists to sell 100+ million records solo AND with a band",
    "The first digital music file was created in 1981 at Lucasfilm",
    "The intro to 'Money' by Pink Floyd is in 7/4 time",
    "Beethoven composed some of his best work after going deaf",
    "The 'Abbey Road' crosswalk has been repainted every 3 months since 1969",
    "'Mary Had a Little Lamb' was the first audio recording ever made (1877)",
]


class StereoVisualizer:
    """A retro 80s-style stereo visualizer with bouncing bars."""

    def __init__(
        self,
        num_bars: int = 16,
        max_height: int = 8,
        console: Console | None = None,
    ):
        self.num_bars = num_bars
        self.max_height = max_height
        self.console = console or Console()

        # Current bar heights (0.0 to 1.0)
        self._heights = [0.0] * num_bars
        # Target heights (bars animate toward these)
        self._targets = [0.0] * num_bars
        # Peak indicators (the "floating" peak dots)
        self._peaks = [0.0] * num_bars
        # Peak decay velocity
        self._peak_velocity = [0.0] * num_bars

        # Progress state
        self._progress = 0.0
        self._current_file = ""
        self._status_message = "Initializing..."
        self._files_processed = 0
        self._total_files = 0

        # Trivia state
        self._current_trivia = random.choice(MUSIC_TRIVIA)
        self._trivia_change_counter = 0
        self._trivia_change_interval = 50  # Change trivia every ~50 updates
        self._last_trivia_time = time.time()

        # Live display
        self._live: Live | None = None

        # Background animation thread
        self._stop_event = Event()
        self._animation_thread: Thread | None = None

    def _get_bar_color(self, height: float) -> str:
        """Get color based on bar height - green, amber, red like classic VU meters."""
        if height > 0.85:
            return "red"
        elif height > 0.6:
            return "yellow"
        else:
            return "green"

    def _animate_step(self):
        """Perform one animation step - update heights and peaks."""
        for i in range(self.num_bars):
            # Generate new random targets periodically
            base_activity = 0.3 + (self._progress * 0.5)
            if random.random() < 0.3:  # 30% chance to update target
                wave = abs((i - self.num_bars / 2) / (self.num_bars / 2))
                self._targets[i] = random.random() * base_activity * (1.2 - wave * 0.4)

            # Animate bars toward targets (smooth movement)
            diff = self._targets[i] - self._heights[i]
            self._heights[i] += diff * 0.3

            # Update peaks
            if self._heights[i] > self._peaks[i]:
                self._peaks[i] = self._heights[i]
                self._peak_velocity[i] = 0
            else:
                # Peaks fall slowly with gravity
                self._peak_velocity[i] += 0.02
                self._peaks[i] -= self._peak_velocity[i]
                if self._peaks[i] < 0:
                    self._peaks[i] = 0

    def _render_bars(self) -> Text:
        """Render the visualizer bars."""
        lines = []

        # Build from top to bottom
        for row in range(self.max_height, 0, -1):
            line = Text()
            threshold = row / self.max_height

            for i, (height, peak) in enumerate(zip(self._heights, self._peaks)):
                # Add spacing between bars
                if i > 0:
                    line.append(" ")

                # Check if this cell should be lit
                if height >= threshold:
                    color = self._get_bar_color(threshold)
                    line.append("█", style=f"bold {color}")
                elif peak >= threshold and peak < threshold + (1 / self.max_height):
                    # Peak indicator (floating dot)
                    line.append("─", style="bold white")
                else:
                    line.append(" ", style="dim")

            lines.append(line)

        # Combine lines
        result = Text()
        for i, line in enumerate(lines):
            if i > 0:
                result.append("\n")
            result.append(line)

        return result

    def _render(self) -> Panel:
        """Render the full visualizer display."""
        # Animate one step each render
        self._animate_step()

        bars = self._render_bars()

        # Progress info
        if self._total_files > 0:
            pct = int(self._progress * 100)
            info = f"\n\n[bold cyan]{self._files_processed}[/bold cyan] / [dim]{self._total_files}[/dim] files  [bold white]{pct}%[/bold white]"
            if self._current_file:
                # Truncate filename if too long
                fname = self._current_file
                if len(fname) > 40:
                    fname = "..." + fname[-37:]
                info += f"\n[dim]{fname}[/dim]"
        else:
            info = f"\n\n[dim]{self._status_message}[/dim]"

        # Change trivia every 8 seconds based on time
        if time.time() - self._last_trivia_time > 8:
            self._current_trivia = random.choice(MUSIC_TRIVIA)
            self._last_trivia_time = time.time()

        # Add trivia
        trivia_display = self._current_trivia
        if len(trivia_display) > 65:
            # Word wrap long trivia
            words = trivia_display.split()
            lines = []
            current_line = []
            for word in words:
                if len(' '.join(current_line + [word])) > 65:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    current_line.append(word)
            if current_line:
                lines.append(' '.join(current_line))
            trivia_display = '\n'.join(lines)

        info += f"\n\n[italic dim cyan]💡 {trivia_display}[/italic dim cyan]"

        content = Text()
        content.append(bars)
        content.append_text(Text.from_markup(info))

        return Panel(
            content,
            title="[bold red]♪[/bold red] [bold yellow]MUSIC[/bold yellow] [bold green]ORGANIZER[/bold green] [bold red]♪[/bold red]",
            subtitle="[dim]< press Ctrl+C to stop >[/dim]",
            border_style="bright_blue",
        )

    def set_status(self, message: str):
        """Update the status message (for initialization phase)."""
        self._status_message = message
        # Spike some bars to show activity
        spike_bars = random.sample(range(self.num_bars), k=min(3, self.num_bars))
        for i in spike_bars:
            self._targets[i] = min(1.0, random.uniform(0.2, 0.5))

        if self._live:
            self._live.update(self._render())

    def update(self, current: int, total: int, filename: str):
        """Update progress - called from main thread."""
        self._files_processed = current
        self._total_files = total
        self._progress = current / total if total > 0 else 0
        self._current_file = filename

        # Spike the bars when processing a file
        spike_bars = random.sample(range(self.num_bars), k=min(5, self.num_bars))
        for i in spike_bars:
            self._targets[i] = min(1.0, self._targets[i] + random.uniform(0.3, 0.6))

        # Change trivia periodically
        self._trivia_change_counter += 1
        if self._trivia_change_counter >= self._trivia_change_interval:
            self._current_trivia = random.choice(MUSIC_TRIVIA)
            self._trivia_change_counter = 0

        # Force refresh the display
        if self._live:
            self._live.update(self._render())

    def _animation_loop(self):
        """Background animation loop to keep bars moving."""
        while not self._stop_event.is_set():
            if self._live:
                # Random bar activity even without file updates
                for i in range(self.num_bars):
                    if random.random() < 0.2:
                        self._targets[i] = random.uniform(0.1, 0.4)
                try:
                    self._live.update(self._render())
                except Exception:
                    pass  # Ignore errors during shutdown
            time.sleep(0.1)  # ~10 fps background animation

    def start(self) -> Live:
        """Start the visualizer and return the Live context."""
        self._stop_event.clear()
        self._live = Live(
            self._render(),
            console=self.console,
            refresh_per_second=15,
            transient=False,  # Keep output visible
        )
        self._live.start()

        # Start background animation thread
        self._animation_thread = Thread(target=self._animation_loop, daemon=True)
        self._animation_thread.start()

        return self._live

    def stop(self, live: Live):
        """Stop the visualizer."""
        # Stop background animation
        self._stop_event.set()
        if self._animation_thread:
            self._animation_thread.join(timeout=1.0)

        live.stop()
        self._live = None

        # Final render showing completion
        self.console.print(Panel(
            "[bold green]✓ Complete![/bold green]\n\n"
            f"Processed [bold cyan]{self._files_processed}[/bold cyan] files",
            title="[bold red]♪[/bold red] [bold yellow]MUSIC[/bold yellow] [bold green]ORGANIZER[/bold green] [bold red]♪[/bold red]",
            border_style="green",
        ))
