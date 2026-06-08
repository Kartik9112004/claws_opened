"""
modes/agent/orchestrator.py — CLI Agent Mode: prompt → tool loop → approval → apply.
"""
from __future__ import annotations

import questionary
from rich.console import Console

from ai.client import run_tool_loop
from config import CODEBASE_PATH, LLM_DEFAULT_MODEL
from modes.agent.executor import ToolExecutor
from modes.agent.tracker import ActionTracker
from modes.agent.tools import create_agent_tools
from modes.agent.approval import run_approval_flow
from tui.terminal_md import render_markdown

_console = Console()

SYSTEM_PROMPT = (
    "You are an autonomous coding agent. You have tools to read and modify the filesystem. "
    "All file mutations are staged and require user approval before being applied to disk. "
    "Be precise. Think step by step. Use semantic_search_codebase to understand code before modifying it.\n\n"
    "PATH RULES:\n"
    "- For files INSIDE the workspace, use relative paths (e.g. 'add.py', 'src/utils.py').\n"
    "- For files OUTSIDE the workspace (e.g. /Users/kartikbudhani/Desktop/file.py), use the full absolute path.\n"
    "- If the user specifies a directory (e.g. 'Desktop'), infer a sensible filename yourself and use the full path "
    "(e.g. /Users/kartikbudhani/Desktop/add_numbers.py).\n"
    "- NEVER ask the user for a filename when the task is clear. Infer it and act immediately."
)


def run_agent_mode() -> None:
    _console.print("\n[bold green]🤖 Agent Mode[/bold green]\n")

    goal = questionary.text(
        "What would you like the agent to do?",
        instruction="(Describe a concrete task for this codebase)",
    ).ask()

    if not goal or not goal.strip():
        return

    tracker = ActionTracker()
    executor = ToolExecutor(tracker, CODEBASE_PATH)
    tool_schemas, tool_executors = create_agent_tools(executor)

    messages = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\nWorkspace root: {CODEBASE_PATH}"},
        {"role": "user", "content": goal.strip()},
    ]

    _console.print("\n[cyan]⚙️  Agent working...[/cyan]\n")

    def on_tool_call(name: str, args: dict) -> None:
        preview = str(args)[:160]
        _console.print(f"  [green]✓[/green] [bold]{name}[/bold] [dim]{preview}[/dim]")

    final_text, _ = run_tool_loop(
        messages=messages,
        tools=tool_schemas,
        tool_executors=tool_executors,
        model=LLM_DEFAULT_MODEL,
        max_steps=40,
        on_tool_call=on_tool_call,
    )

    if final_text.strip():
        _console.print()
        render_markdown(final_text)

    approved = run_approval_flow(tracker, executor)
    if not approved:
        executor.clear_staging()
        return

    errors = executor.apply_approved()
    executor.clear_staging()

    if errors:
        _console.print("\n[red]Some operations reported errors:[/red]")
        for err in errors:
            _console.print(f"  [red]• {err}[/red]")
    else:
        _console.print("\n[bold green]✓ All changes applied.[/bold green]\n")
