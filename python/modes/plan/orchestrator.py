"""
modes/plan/orchestrator.py — CLI Plan Mode: generate plan → select steps → execute each.
"""
from __future__ import annotations

import questionary
from rich.console import Console
from rich.table import Table

from modes.plan.planner import generate_plan, Plan, PlanStep
from modes.agent.executor import ToolExecutor
from modes.agent.tracker import ActionTracker
from modes.agent.tools import create_agent_tools
from modes.agent.approval import run_approval_flow
from ai.client import run_tool_loop
from config import CODEBASE_PATH, LLM_DEFAULT_MODEL
from tui.terminal_md import render_markdown

_console = Console()


def _print_plan(plan: Plan, selected: set[str]) -> None:
    table = Table(title=f"📋 Plan: {plan.goal}", show_lines=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold")
    table.add_column("Complexity")
    table.add_column("Selected")

    for step in plan.steps:
        tick = "[green]✓[/green]" if step.id in selected else "[dim]○[/dim]"
        colour = {"low": "green", "medium": "yellow", "high": "red"}.get(step.complexity, "white")
        table.add_row(step.id, step.title, f"[{colour}]{step.complexity}[/{colour}]", tick)
    _console.print(table)


def run_plan_mode() -> None:
    _console.print("\n[bold cyan]🧭 Plan Mode[/bold cyan]\n")

    goal = questionary.text("What is your goal?").ask()
    if not goal or not goal.strip():
        return

    _console.print("\n[cyan]🔍 Researching & drafting a plan…[/cyan]\n")
    plan = generate_plan(goal.strip())

    if not plan.steps:
        _console.print("[red]No plan steps generated.[/red]")
        return

    if plan.research_summary:
        _console.print(f"[dim italic]{plan.research_summary}[/dim italic]\n")

    # Let user select which steps to run
    step_choices = [
        questionary.Choice(title=f"[{s.complexity}] {s.title}", value=s.id)
        for s in plan.steps
    ]
    selected_ids = questionary.checkbox(
        "Select steps to execute:",
        choices=step_choices,
        instruction="(Space to toggle, Enter to confirm)",
    ).ask()

    if not selected_ids:
        _console.print("[dim]No steps selected.[/dim]")
        return

    selected_steps = [s for s in plan.steps if s.id in selected_ids]

    tracker = ActionTracker()
    executor = ToolExecutor(tracker, CODEBASE_PATH)
    tool_schemas, tool_executors = create_agent_tools(executor)

    for step in selected_steps:
        _console.print(f"\n[bold]🔧 Executing:[/bold] {step.title}")
        prompt = f"Goal: {plan.goal}\nStep: {step.title}\n{step.description}"
        if step.hints:
            prompt += "\nHints:\n" + "\n".join(f"- {h}" for h in step.hints)

        messages = [
            {"role": "system", "content": f"Workspace root: {CODEBASE_PATH}"},
            {"role": "user", "content": prompt},
        ]
        text, _ = run_tool_loop(
            messages=messages,
            tools=tool_schemas,
            tool_executors=tool_executors,
            model=LLM_DEFAULT_MODEL,
            max_steps=30,
        )
        if text.strip():
            render_markdown(text)

    approved = run_approval_flow(tracker, executor)
    if not approved:
        executor.clear_staging()
        return

    errors = executor.apply_approved()
    executor.clear_staging()
    if errors:
        for err in errors:
            _console.print(f"[red]• {err}[/red]")
    else:
        _console.print("\n[bold green]✓ All plan steps applied.[/bold green]\n")
