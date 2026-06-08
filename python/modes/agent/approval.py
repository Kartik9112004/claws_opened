"""
modes/agent/approval.py — Interactive CLI approval flow using questionary + rich diffs.
"""
from __future__ import annotations

import questionary
from rich.console import Console

from modes.agent.tracker import ActionTracker, ActionLog
from modes.agent.diff_view import render_diff
from modes.agent.executor import ToolExecutor

_console = Console()


def run_approval_flow(tracker: ActionTracker, executor: ToolExecutor) -> bool:
    """
    Show pending staged mutations and ask the user to approve or reject.

    Returns True if the user approved (all or selected), False otherwise.
    """
    pending = tracker.get_pending_mutations()

    if not pending:
        _console.print("\n[dim]No staged changes to review.[/dim]\n")
        return False

    # Summarise pending actions
    _console.print(f"\n[bold yellow]📋 {len(pending)} staged change(s):[/bold yellow]")
    for a in pending:
        icon = {"file_create": "➕", "file_modify": "✏️ ", "file_delete": "🗑️ ",
                "folder_create": "📁", "tool_execute": "🖥️ "}.get(a.type, "•")
        label = a.details.get("command", a.path) if a.type == "tool_execute" else a.path
        _console.print(f"  {icon} [{a.type}] {label}")

    choice = questionary.select(
        "\nApply staged changes?",
        choices=["Approve and apply all", "Review one by one", "Cancel"],
    ).ask()

    if not choice or choice == "Cancel":
        for a in pending:
            tracker.update_status(a.id, "rejected", False)
        return False

    if choice == "Approve and apply all":
        for a in pending:
            tracker.update_status(a.id, "approved", True)
        return True

    # Review one by one
    approved_any = False
    for a in pending:
        _console.print(f"\n[bold]Action:[/bold] [{a.type}] {a.path}")
        if a.type in ("file_create", "file_modify") and "after" in a.details:
            before = a.details.get("before", "")
            after = a.details["after"]
            render_diff(a.path, before, after)
        elif a.type == "file_delete":
            _console.print(f"[red]  Will delete: {a.path}[/red]")
        elif a.type == "tool_execute":
            _console.print(f"[yellow]  Shell: {a.details.get('command')}[/yellow]")

        ok = questionary.confirm("Apply this change?", default=True).ask()
        if ok:
            tracker.update_status(a.id, "approved", True)
            approved_any = True
        else:
            tracker.update_status(a.id, "rejected", False)

    return approved_any
