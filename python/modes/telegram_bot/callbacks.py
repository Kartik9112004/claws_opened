"""
modes/telegram_bot/callbacks.py — InlineKeyboard button handlers for plan and approval flows.
"""
from __future__ import annotations

import asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import TELEGRAM_OWNER_ID
from modes.agent.diff_view import format_diff_text
from modes.telegram_bot.sessions import plan_sessions, approval_sessions, PlanSession


def _is_owner(chat_id: int) -> bool:
    return chat_id == TELEGRAM_OWNER_ID


def _plan_keyboard(session: PlanSession) -> InlineKeyboardMarkup:
    rows = []
    for step in session.plan.steps:
        tick = "✅" if step.id in session.selected else "⬜"
        rows.append([InlineKeyboardButton(
            f"{tick} {step.title}",
            callback_data=f"plan_toggle:{step.id}",
        )])
    rows.append([
        InlineKeyboardButton("☑️ All", callback_data="plan_all"),
        InlineKeyboardButton("◻️ None", callback_data="plan_none"),
        InlineKeyboardButton("🚀 Execute", callback_data="plan_proceed"),
    ])
    return InlineKeyboardMarkup(rows)


def _plan_message(session: PlanSession) -> str:
    lines = [f"*📋 Plan: {session.plan.goal}*\n"]
    for step in session.plan.steps:
        tick = "✅" if step.id in session.selected else "⬜"
        lines.append(f"{tick} *{step.title}* _{step.complexity}_\n_{step.description}_")
    return "\n\n".join(lines)


async def handle_plan_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    if not _is_owner(chat_id):
        await query.answer()
        return

    session = plan_sessions.get(chat_id)
    if not session:
        await query.answer("Session expired.")
        return

    step_id = query.data.split(":", 1)[1]
    if step_id in session.selected:
        session.selected.discard(step_id)
    else:
        session.selected.add(step_id)

    await query.edit_message_text(_plan_message(session), parse_mode="Markdown",
                                   reply_markup=_plan_keyboard(session))
    await query.answer()


async def handle_plan_all(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    if not _is_owner(chat_id):
        await query.answer()
        return
    session = plan_sessions.get(chat_id)
    if session:
        session.selected = {s.id for s in session.plan.steps}
        await query.edit_message_text(_plan_message(session), parse_mode="Markdown",
                                       reply_markup=_plan_keyboard(session))
    await query.answer()


async def handle_plan_none(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    if not _is_owner(chat_id):
        await query.answer()
        return
    session = plan_sessions.get(chat_id)
    if session:
        session.selected.clear()
        await query.edit_message_text(_plan_message(session), parse_mode="Markdown",
                                       reply_markup=_plan_keyboard(session))
    await query.answer()


async def handle_plan_proceed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from modes.telegram_bot.handlers import run_plan_steps_task
    query = update.callback_query
    chat_id = query.message.chat_id
    if not _is_owner(chat_id):
        await query.answer()
        return

    session = plan_sessions.pop(chat_id, None)
    if not session or not session.selected:
        await query.answer("No steps selected.")
        return

    steps = [s for s in session.plan.steps if s.id in session.selected]
    names = "\n".join(f"{i+1}. {s.title}" for i, s in enumerate(steps))
    await query.edit_message_text(f"🚀 Executing {len(steps)} step(s)…\n\n{names}")
    await query.answer()

    asyncio.create_task(run_plan_steps_task(query.message, session.plan, steps))


async def handle_approval_diff(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    if not _is_owner(chat_id):
        await query.answer()
        return

    session = approval_sessions.get(chat_id)
    if not session:
        await query.answer("No pending approval.")
        return

    pending = session.tracker.get_pending_mutations()
    parts = []
    for a in pending:
        if a.type in ("file_create", "file_modify"):
            diff = format_diff_text(a.path, a.details.get("before", ""), a.details.get("after", ""))
            parts.append(diff[:1500])
        elif a.type == "file_delete":
            parts.append(f"DELETE {a.path}")
        elif a.type == "tool_execute":
            parts.append(f"SHELL: {a.details.get('command')}")

    text = "\n\n".join(parts)[:4000] or "(no diff)"
    await query.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")
    await query.answer()


async def handle_approval_accept(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    if not _is_owner(chat_id):
        await query.answer()
        return

    session = approval_sessions.pop(chat_id, None)
    if not session:
        await query.answer("No pending approval.")
        return

    for a in session.tracker.get_pending_mutations():
        session.tracker.update_status(a.id, "approved", True)
    errors = session.executor.apply_approved()
    session.executor.clear_staging()

    await query.edit_message_text("✅ All changes applied.")
    await query.answer("Applied!")
    if errors:
        await query.message.reply_text("⚠️ Errors:\n" + "\n".join(errors))


async def handle_approval_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    chat_id = query.message.chat_id
    if not _is_owner(chat_id):
        await query.answer()
        return

    session = approval_sessions.pop(chat_id, None)
    if not session:
        await query.answer("No pending approval.")
        return

    for a in session.tracker.get_pending_mutations():
        session.tracker.update_status(a.id, "rejected", False)
    session.executor.clear_staging()

    await query.edit_message_text("❌ All changes rejected. Nothing was applied.")
    await query.answer("Rejected")
