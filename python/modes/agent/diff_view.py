"""
modes/agent/diff_view.py — Renders unified diffs with rich colours.
"""
from __future__ import annotations

import difflib

from rich.console import Console
from rich.text import Text

_console = Console()


def render_diff(path: str, before: str, after: str) -> None:
    """Print a coloured unified diff for a staged file change."""
    diff = list(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    ))
    if not diff:
        _console.print(f"[dim]No changes in {path}[/dim]")
        return

    _console.print(f"\n[bold cyan]── {path} ──[/bold cyan]")
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            _console.print(Text(line.rstrip(), style="green"))
        elif line.startswith("-") and not line.startswith("---"):
            _console.print(Text(line.rstrip(), style="red"))
        elif line.startswith("@@"):
            _console.print(Text(line.rstrip(), style="cyan"))
        else:
            _console.print(Text(line.rstrip(), style="dim"))


def format_diff_text(path: str, before: str, after: str) -> str:
    """Return the raw unified diff as a string (for Telegram messages)."""
    diff = list(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    ))
    return "".join(diff) or "(no changes)"
