"""
tui/terminal_md.py — Renders markdown strings using rich.
"""
from __future__ import annotations

from rich.console import Console
from rich.markdown import Markdown

_console = Console()


def render_markdown(text: str) -> None:
    """Print markdown-formatted text to the terminal using rich."""
    _console.print(Markdown(text))


def render_markdown_str(text: str) -> str:
    """Render markdown to a plain string (for Telegram or file output)."""
    with _console.capture() as cap:
        _console.print(Markdown(text))
    return cap.get()
