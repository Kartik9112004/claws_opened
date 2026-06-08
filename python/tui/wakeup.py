"""
tui/wakeup.py — Prints the CLAWS_OPENED figlet banner and shows the main mode selector.
"""
from __future__ import annotations

import pyfiglet
import questionary
from rich.console import Console
from rich.text import Text

console = Console()

_SHADOW_COLOR = "#5b4d9e"
_FACE_COLOR = "#e8dcf8"


def print_banner() -> None:
    ascii_art = pyfiglet.figlet_format("CLAWS_OPENED", font="standard")
    lines = ascii_art.rstrip().splitlines()

    # Print shadow offset (2 spaces right + 1 line down) in dim purple
    for line in lines:
        console.print(Text("  " + line, style=f"bold {_SHADOW_COLOR}"))

    # Overprint face in bright lavender using ANSI cursor-up trick
    print(f"\x1b[{len(lines)}A", end="")
    for line in lines:
        console.print(Text(line, style=f"bold {_FACE_COLOR}"))

    console.print()


def run_wakeup() -> None:
    from modes.agent.orchestrator import run_agent_mode
    from modes.plan.orchestrator import run_plan_mode
    from modes.ask.orchestrator import run_ask_mode
    from modes.telegram_bot.bot import run_telegram_mode

    print_banner()

    mode = questionary.select(
        "Which mode do you want to proceed with?",
        choices=["CLI", "Telegram", "Exit"],
    ).ask()

    if not mode or mode == "Exit":
        console.print("\n[dim] Goodbye. [/dim]\n")
        return

    if mode == "Telegram":
        run_telegram_mode()
        return

    # CLI sub-mode loop
    while True:
        sub = questionary.select(
            "Choose CLI sub-mode:",
            choices=["Agent Mode", "Plan Mode", "Ask Mode", "← Back"],
        ).ask()

        if not sub or sub == "← Back":
            return
        if sub == "Agent Mode":
            run_agent_mode()
        elif sub == "Plan Mode":
            run_plan_mode()
        elif sub == "Ask Mode":
            run_ask_mode()
