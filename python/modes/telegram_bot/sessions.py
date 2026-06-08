"""
modes/telegram_bot/sessions.py — In-memory session stores for plan and approval flows.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from modes.plan.planner import Plan, PlanStep
from modes.agent.tracker import ActionTracker
from modes.agent.executor import ToolExecutor


@dataclass
class PlanSession:
    plan: Plan
    selected: set[str] = field(default_factory=set)  # selected step IDs


@dataclass
class ApprovalSession:
    tracker: ActionTracker
    executor: ToolExecutor


# Keyed by Telegram chat_id (int)
plan_sessions: dict[int, PlanSession] = {}
approval_sessions: dict[int, ApprovalSession] = {}
