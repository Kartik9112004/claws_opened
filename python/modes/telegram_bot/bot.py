"""
modes/telegram_bot/bot.py — Builds and runs the Telegram bot application.
"""
from __future__ import annotations

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
)

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_OWNER_ID
from modes.telegram_bot.handlers import cmd_start, cmd_ask, cmd_agent, cmd_plan
from modes.telegram_bot.callbacks import (
    handle_plan_toggle,
    handle_plan_all,
    handle_plan_none,
    handle_plan_proceed,
    handle_approval_diff,
    handle_approval_accept,
    handle_approval_reject,
)


def run_telegram_mode() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN is not set.")
        return

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("ask", cmd_ask))
    app.add_handler(CommandHandler("agent", cmd_agent))
    app.add_handler(CommandHandler("plan", cmd_plan))

    # Plan inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(handle_plan_toggle, pattern=r"^plan_toggle:.+$"))
    app.add_handler(CallbackQueryHandler(handle_plan_all, pattern="^plan_all$"))
    app.add_handler(CallbackQueryHandler(handle_plan_none, pattern="^plan_none$"))
    app.add_handler(CallbackQueryHandler(handle_plan_proceed, pattern="^plan_proceed$"))

    # Approval inline keyboard callbacks
    app.add_handler(CallbackQueryHandler(handle_approval_diff, pattern="^approval_diff$"))
    app.add_handler(CallbackQueryHandler(handle_approval_accept, pattern="^approval_accept$"))
    app.add_handler(CallbackQueryHandler(handle_approval_reject, pattern="^approval_reject$"))

    print(f"🤖 Telegram bot running (owner: {TELEGRAM_OWNER_ID}). Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)
