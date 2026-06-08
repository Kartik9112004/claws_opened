"""
modes/telegram_bot/handlers.py — /start /ask /agent /plan command handlers.
All agent runs are wrapped in asyncio.create_task() — non-blocking.
"""
from __future__ import annotations

import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
from telegram.ext import ContextTypes

from ai.client import run_tool_loop
from config import TELEGRAM_OWNER_ID, CODEBASE_PATH, LLM_DEFAULT_MODEL
from db.session_store import load_chat_history, save_message
from db.rag_service import semantic_search
from modes.agent.executor import ToolExecutor
from modes.agent.tracker import ActionTracker
from modes.agent.tools import create_agent_tools
from modes.plan.planner import Plan, PlanStep, generate_plan
from modes.plan.web_tools import create_web_tools
from modes.telegram_bot.sessions import (
    plan_sessions, approval_sessions, PlanSession, ApprovalSession,
)


def _is_owner(chat_id: int) -> bool:
    return chat_id == TELEGRAM_OWNER_ID


def _clip(text: str, n: int = 4000) -> str:
    return text[:n] + "\n…[truncated]" if len(text) > n else text


async def _reply_md(message: Message, text: str) -> None:
    """Send a Telegram message in Markdown, falling back to plain text."""
    try:
        await message.reply_text(_clip(text), parse_mode="Markdown")
    except Exception:
        await message.reply_text(_clip(text))


def _approval_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Show Diff", callback_data="approval_diff")],
        [
            InlineKeyboardButton("✅ Accept All", callback_data="approval_accept"),
            InlineKeyboardButton("❌ Reject All", callback_data="approval_reject"),
        ],
    ])


def _approval_summary(tracker: ActionTracker) -> str:
    pending = tracker.get_pending_mutations()
    if not pending:
        return "No changes staged."
    lines = []
    for a in pending:
        icon = {"file_create": "➕", "file_modify": "✏️", "file_delete": "🗑",
                "folder_create": "📁", "tool_execute": "🖥"}.get(a.type, "•")
        label = a.details.get("command", a.path) if a.type == "tool_execute" else a.path
        lines.append(f"{icon} `{label}`")
    return f"*📋 {len(pending)} staged change(s):*\n" + "\n".join(lines)


async def _finish_or_approve(message: Message, chat_id: int,
                              tracker: ActionTracker, executor: ToolExecutor,
                              no_changes_msg: str) -> None:
    pending = tracker.get_pending_mutations()
    if not pending:
        await message.reply_text(no_changes_msg)
        return
    approval_sessions[chat_id] = ApprovalSession(tracker=tracker, executor=executor)
    await message.reply_text(
        _approval_summary(tracker),
        parse_mode="Markdown",
        reply_markup=_approval_keyboard(),
    )


# ── Background task runners ──────────────────────────────────────────────────

async def _run_ask_task(message: Message, chat_id: int, question: str) -> None:
    tracker = ActionTracker()
    executor = ToolExecutor(tracker, CODEBASE_PATH)

    def _fmt(results: list[dict]) -> str:
        return "\n\n".join(
            f"Match #{i+1}: {r['file_path']}\n```\n{r['content']}\n```"
            for i, r in enumerate(results)
        ) if results else "No results."

    web_schemas, web_executors = create_web_tools()
    tool_schemas = [
        {"type": "function", "function": {"name": "semantic_search_codebase",
            "description": "Semantic search.", "parameters": {"type": "object",
            "properties": {"query": {"type": "string"}, "k": {"type": "integer", "default": 5}},
            "required": ["query"]}}},
        {"type": "function", "function": {"name": "read_file", "description": "Read file.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "list_files", "description": "List files.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"},
            "recursive": {"type": "boolean", "default": False}}, "required": ["path"]}}},
    ] + web_schemas

    tool_executors = {
        "semantic_search_codebase": lambda query, k=5: _fmt(semantic_search(query, k)),
        "read_file": executor.read_file,
        "list_files": executor.list_files,
        **web_executors,
    }

    chat_name = f"Telegram {chat_id}"
    messages = [
        {"role": "system", "content": (
            "You are in Ask Mode — read-only access to the workspace. "
            f"Workspace root: {CODEBASE_PATH}"
        )},
    ]
    messages.extend(load_chat_history(str(chat_id)))
    messages.append({"role": "user", "content": question})

    answer, _ = run_tool_loop(
        messages=messages,
        tools=tool_schemas,
        tool_executors=tool_executors,
        model=LLM_DEFAULT_MODEL,
        max_steps=20,
    )
    answer = answer or "(no answer)"
    await _reply_md(message, answer)
    save_message(str(chat_id), "user", question, chat_name)
    save_message(str(chat_id), "assistant", answer, chat_name)


async def _run_agent_task(message: Message, chat_id: int, goal: str) -> None:
    tracker = ActionTracker()
    executor = ToolExecutor(tracker, CODEBASE_PATH)
    tool_schemas, tool_executors = create_agent_tools(executor)

    messages = [
        {"role": "system", "content": f"Workspace root: {CODEBASE_PATH}"},
        {"role": "user", "content": goal},
    ]
    answer, _ = run_tool_loop(
        messages=messages,
        tools=tool_schemas,
        tool_executors=tool_executors,
        model=LLM_DEFAULT_MODEL,
        max_steps=40,
    )
    if answer.strip():
        await _reply_md(message, answer.strip())
    await _finish_or_approve(message, chat_id, tracker, executor, "✅ Done. No file changes needed.")


async def run_plan_steps_task(message: Message, plan: Plan, steps: list[PlanStep]) -> None:
    tracker = ActionTracker()
    executor = ToolExecutor(tracker, CODEBASE_PATH)
    tool_schemas, tool_executors = create_agent_tools(executor)
    web_schemas, web_executors = create_web_tools()
    all_schemas = tool_schemas + web_schemas
    all_executors = {**tool_executors, **web_executors}

    for step in steps:
        await message.reply_text(f"🔧 Executing: *{step.title}*", parse_mode="Markdown")
        prompt = f"Goal: {plan.goal}\nStep: {step.title}\n{step.description}"
        messages = [
            {"role": "system", "content": f"Workspace root: {CODEBASE_PATH}"},
            {"role": "user", "content": prompt},
        ]
        text, _ = run_tool_loop(
            messages=messages,
            tools=all_schemas,
            tool_executors=all_executors,
            model=LLM_DEFAULT_MODEL,
            max_steps=30,
        )
        if text.strip():
            await _reply_md(message, text.strip())

    await _finish_or_approve(message, message.chat_id, tracker, executor,
                             "✅ All steps done. No file changes needed.")


# ── Command handlers ──────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_owner(update.effective_chat.id):
        return
    await update.message.reply_text(
        "👋 *Claws Opened Bot*\n\nCommands:\n"
        "/ask `<question>` — Read-only Q\\&A\n"
        "/agent `<task>` — Autonomous coding agent\n"
        "/plan `<goal>` — Structured plan\\→execute",
        parse_mode="Markdown",
    )


async def cmd_ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not _is_owner(chat_id):
        return
    text = update.message.text or ""
    question = text[len("/ask"):].strip()
    if not question:
        await update.message.reply_text("Usage: `/ask <your question>`", parse_mode="Markdown")
        return
    await update.message.reply_text("🔍 Researching your question…")
    asyncio.create_task(_run_ask_task(update.message, chat_id, question))


async def cmd_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not _is_owner(chat_id):
        return
    text = update.message.text or ""
    goal = text[len("/agent"):].strip()
    if not goal:
        await update.message.reply_text("Usage: `/agent <task description>`", parse_mode="Markdown")
        return
    await update.message.reply_text("🤖 Agent is working on your task…")
    asyncio.create_task(_run_agent_task(update.message, chat_id, goal))


async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from modes.telegram_bot.callbacks import _plan_keyboard, _plan_message
    chat_id = update.effective_chat.id
    if not _is_owner(chat_id):
        return
    text = update.message.text or ""
    goal = text[len("/plan"):].strip()
    if not goal:
        await update.message.reply_text("Usage: `/plan <your goal>`", parse_mode="Markdown")
        return
    await update.message.reply_text("🧭 Generating a plan…")

    async def _gen() -> None:
        plan = generate_plan(goal)
        session = PlanSession(plan=plan, selected={s.id for s in plan.steps})
        plan_sessions[chat_id] = session
        await update.message.reply_text(
            _plan_message(session),
            parse_mode="Markdown",
            reply_markup=_plan_keyboard(session),
        )

    asyncio.create_task(_gen())
