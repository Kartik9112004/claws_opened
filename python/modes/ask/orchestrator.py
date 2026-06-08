"""
modes/ask/orchestrator.py — Interactive read-only multi-turn chat with codebase access.
Saves/resumes chat history via Supabase.
"""
from __future__ import annotations

import uuid
from datetime import date

import questionary
from rich.console import Console

from ai.client import run_tool_loop
from config import CODEBASE_PATH, LLM_DEFAULT_MODEL
from db.session_store import load_chat_history, save_message, list_chats, create_chat
from db.rag_service import semantic_search
from modes.agent.executor import ToolExecutor
from modes.agent.tracker import ActionTracker
from tui.terminal_md import render_markdown
from modes.plan.web_tools import create_web_tools

_console = Console()

SYSTEM_PROMPT = (
    "You are in Ask Mode — read-only access to the workspace. "
    "You MUST use the provided tools to inspect files and answer questions. "
    "Never refuse to access files. Use semantic_search_codebase for concept-level questions."
)


def _build_ask_tools(executor: ToolExecutor) -> tuple[list[dict], dict]:
    def _fmt(results: list[dict]) -> str:
        if not results:
            return "No relevant code snippets found."
        return "\n\n".join(
            f"Match #{i+1}: {r['file_path']} ({r['similarity']*100:.1f}%)\n```\n{r['content']}\n```"
            for i, r in enumerate(results)
        )

    schemas = [
        {"type": "function", "function": {"name": "semantic_search_codebase",
            "description": "Semantic search of the codebase.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"}, "k": {"type": "integer", "default": 5}},
                "required": ["query"]}}},
        {"type": "function", "function": {"name": "read_file",
            "description": "Read a workspace file.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "list_files",
            "description": "List files under a path.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "recursive": {"type": "boolean", "default": False}},
                "required": ["path"]}}},
        {"type": "function", "function": {"name": "search_files",
            "description": "Glob file search.",
            "parameters": {"type": "object", "properties": {
                "root": {"type": "string"}, "pattern": {"type": "string"},
                "content_contains": {"type": "string"}}, "required": ["root", "pattern"]}}},
        {"type": "function", "function": {"name": "analyze_codebase",
            "description": "Summarise codebase structure.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}, "required": []}}},
    ]
    executors = {
        "semantic_search_codebase": lambda query, k=5: _fmt(semantic_search(query, k)),
        "read_file": executor.read_file,
        "list_files": executor.list_files,
        "search_files": executor.search_files,
        "analyze_codebase": executor.analyze_codebase,
    }
    # Merge web tools if configured
    web_schemas, web_executors = create_web_tools()
    return schemas + web_schemas, {**executors, **web_executors}


def run_ask_mode() -> None:
    _console.print("\n[bold blue]❓ Ask Mode (Interactive Chat)[/bold blue]")
    _console.print(f"[dim]📂 Workspace: {CODEBASE_PATH}[/dim]\n")

    tracker = ActionTracker()
    executor = ToolExecutor(tracker, CODEBASE_PATH)
    tool_schemas, tool_executors = _build_ask_tools(executor)

    # Chat session management
    chat_id = "cli_ask_mode"
    chat_name = "Default CLI Chat"
    existing_chats = list_chats()

    if existing_chats:
        choice = questionary.select(
            "Start a new chat or resume an existing one?",
            choices=["New chat", "Resume existing"],
        ).ask()

        if choice == "Resume existing":
            selected = questionary.select(
                "Choose a chat:",
                choices=[questionary.Choice(c["name"], value=c["id"]) for c in existing_chats],
            ).ask()
            if selected:
                chat_id = selected
                chat_name = next((c["name"] for c in existing_chats if c["id"] == selected), selected)

    if chat_id == "cli_ask_mode":
        name_input = questionary.text(
            "Name this chat session:",
            default=f"Chat - {date.today().isoformat()}",
        ).ask()
        chat_name = name_input.strip() if name_input and name_input.strip() else chat_name
        chat_id = str(uuid.uuid4())
        create_chat(chat_id, chat_name)

    messages: list[dict] = [
        {"role": "system", "content": f"{SYSTEM_PROMPT}\nWorkspace root: {CODEBASE_PATH}"},
    ]
    history = load_chat_history(chat_id)
    messages.extend(history)
    if history:
        _console.print(f"[green]📂 Resumed \"{chat_name}\" ({len(history)} messages)[/green]\n")
    else:
        _console.print(f"[green]📂 Started new chat: \"{chat_name}\"[/green]\n")

    _console.print("[dim]Type your questions. Press Enter on empty line or type 'exit' to finish.[/dim]\n")

    chat_log: list[dict] = []

    while True:
        question = questionary.text("Ask:").ask()
        if not question or question.strip().lower() in ("", "exit"):
            break

        messages.append({"role": "user", "content": question.strip()})
        _console.print("[cyan]\n🤖 Thinking…[/cyan]")

        def on_tool(name: str, args: dict) -> None:
            _console.print(f"  [green]✓[/green] [bold]{name}[/bold] [dim]{str(args)[:120]}[/dim]")

        answer, messages = run_tool_loop(
            messages=messages,
            tools=tool_schemas,
            tool_executors=tool_executors,
            model=LLM_DEFAULT_MODEL,
            max_steps=20,
            on_tool_call=on_tool,
        )
        answer = answer or "(no answer)"
        _console.print()
        render_markdown(answer)

        chat_log.append({"question": question.strip(), "answer": answer})
        save_message(chat_id, "user", question.strip(), chat_name)
        save_message(chat_id, "assistant", answer, chat_name)

    if not chat_log:
        return

    save_md = questionary.confirm("Save this conversation to a .md file?", default=False).ask()
    if save_md:
        fname = questionary.text("Filename:", default="ask.md").ask() or "ask.md"
        if not fname.endswith(".md"):
            fname += ".md"
        md = "# Ask Mode Conversation\n\n"
        for i, turn in enumerate(chat_log, 1):
            md += f"## Q{i}: {turn['question']}\n\n{turn['answer']}\n\n---\n\n"
        import os
        out_path = os.path.join(CODEBASE_PATH, fname)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(md)
        _console.print(f"[green]✓ Saved to {out_path}[/green]")
