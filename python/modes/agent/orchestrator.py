"""
modes/agent/orchestrator.py — CLI Agent Mode: prompt → tool loop → approval → apply.
"""
from __future__ import annotations

import uuid
from datetime import date

import questionary
from rich.console import Console

from ai.client import run_tool_loop
from config import CODEBASE_PATH, LLM_DEFAULT_MODEL
from modes.agent.executor import ToolExecutor
from modes.agent.tracker import ActionTracker
from modes.agent.tools import create_agent_tools
from modes.agent.approval import run_approval_flow
from db.session_store import load_chat_history, save_message, list_chats, create_chat
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


def _pick_or_create_session() -> tuple[str, str, list[dict]]:
    """
    Let the user pick an existing agent session or start a new one.
    Returns (chat_id, chat_name, prior_messages).
    """
    existing = list_chats()
    prior: list[dict] = []
    chat_id = str(uuid.uuid4())
    chat_name = f"Agent - {date.today().isoformat()}"

    if existing:
        choice = questionary.select(
            "Session:",
            choices=["New session", "Resume existing session"],
        ).ask()

        if choice == "Resume existing session":
            selected = questionary.select(
                "Choose a session:",
                choices=[questionary.Choice(c["name"], value=c["id"]) for c in existing],
            ).ask()
            if selected:
                chat_id = selected
                chat_name = next((c["name"] for c in existing if c["id"] == selected), selected)
                prior = load_chat_history(chat_id)
                if prior:
                    _console.print(f"[green]📂 Resumed \"{chat_name}\" ({len(prior)} messages)[/green]\n")
                return chat_id, chat_name, prior

    # New session — optionally name it
    name_input = questionary.text(
        "Name this session (optional):",
        default=chat_name,
    ).ask()
    chat_name = name_input.strip() if name_input and name_input.strip() else chat_name
    create_chat(chat_id, chat_name)
    return chat_id, chat_name, prior


def run_agent_mode() -> None:
    _console.print("\n[bold green]🤖 Agent Mode[/bold green]\n")

    chat_id, chat_name, prior_messages = _pick_or_create_session()

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
    ]
    # Inject prior session history (skip the old system messages)
    messages.extend(m for m in prior_messages if m.get("role") != "system")
    messages.append({"role": "user", "content": goal.strip()})

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

    # Persist this turn to Supabase
    save_message(chat_id, "user", goal.strip(), chat_name)
    if final_text.strip():
        save_message(chat_id, "assistant", final_text.strip(), chat_name)

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

