"""Rich formatters for the CLI client."""

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

VISIBILITY_COLORS = {"public": "green", "private": "yellow", "delisted": "red"}


def print_error(msg: str) -> None:
    """Print an error message using Rich Console."""
    console.print(f"[bold red]Error:[/bold red] {msg}")


def print_success(msg: str) -> None:
    """Print a success message using Rich Console."""
    console.print(f"[bold green]✓[/bold green] {msg}")


def print_voice_table(items: list, title: str = "Voices") -> None:
    """Print a table of voices using Rich Table.

    Columns: ID (dim, max_width=12), Name, Gender, Age, Duration (right-justify),
    Tags (dim), Votes (yellow, right-justify), Visibility (colored by VISIBILITY_COLORS dict).
    If items is empty, print "No voices found." in yellow.
    """
    if not items:
        console.print("[yellow]No voices found.[/yellow]")
        return

    table = Table(title=title, box=box.ROUNDED)
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Name")
    table.add_column("Gender")
    table.add_column("Age")
    table.add_column("Duration", justify="right")
    table.add_column("Tags", style="dim")
    table.add_column("Votes", style="yellow", justify="right")
    table.add_column("Visibility")

    for item in items:
        visibility = item.get("visibility", "unknown")
        visibility_color = VISIBILITY_COLORS.get(visibility, "white")
        tags = item.get("tags", [])
        tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        duration_ms = item.get("duration_ms")
        duration_str = f"{duration_ms}ms" if duration_ms is not None else "N/A"
        vote_score = item.get("vote_score")
        vote_str = str(vote_score) if vote_score is not None else "N/A"

        table.add_row(
            str(item.get("id", ""))[:12],
            str(item.get("name", "")),
            str(item.get("gender", "")),
            str(item.get("age_group", "")),
            duration_str,
            tags_str,
            vote_str,
            f"[{visibility_color}]{visibility}[/{visibility_color}]",
        )

    console.print(table)


def print_voice_detail(voice: dict) -> None:
    """Print a detailed view of a voice using Rich Panel.

    Shows all voice fields: ID, Name, Gender, Age Group, Language, Duration,
    Sample Rate, Mood, Visibility, Usage Count, Votes, Tags, Description,
    Ref Text, Created.
    """
    visibility = voice.get("visibility", "unknown")
    visibility_color = VISIBILITY_COLORS.get(visibility, "white")
    tags = voice.get("tags", [])
    tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
    duration_ms = voice.get("duration_ms")
    duration_str = f"{duration_ms}ms" if duration_ms is not None else "N/A"
    vote_score = voice.get("vote_score")
    vote_str = str(vote_score) if vote_score is not None else "N/A"

    content = f"""
[bold]ID:[/bold] {voice.get("id", "N/A")}
[bold]Name:[/bold] {voice.get("name", "N/A")}
[bold]Gender:[/bold] {voice.get("gender", "N/A")}
[bold]Age Group:[/bold] {voice.get("age_group", "N/A")}
[bold]Language:[/bold] {voice.get("language", "N/A")}
[bold]Duration:[/bold] {duration_str}
[bold]Sample Rate:[/bold] {voice.get("sample_rate", "N/A")} Hz
[bold]Mood:[/bold] {voice.get("mood", "N/A")}
[bold]Visibility:[/bold] [{visibility_color}]{visibility}[/{visibility_color}]
[bold]Usage Count:[/bold] {voice.get("usage_count", "N/A")}
[bold]Votes:[/bold] {vote_str}
[bold]Tags:[/bold] {tags_str}
[bold]Description:[/bold] {voice.get("description", "N/A")}
[bold]Ref Text:[/bold] {voice.get("ref_text", "N/A")}
[bold]Created:[/bold] {voice.get("created_at", "N/A")}
    """.strip()

    panel = Panel(content, title=f"Voice Details: {voice.get('name', 'Unknown')}", border_style="blue")
    console.print(panel)
