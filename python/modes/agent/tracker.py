"""
modes/agent/tracker.py — ActionTracker logs all staged/executed agent actions.
Mirrors the TypeScript ActionTracker class.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


ActionType = Literal[
    "file_create", "file_modify", "file_delete",
    "folder_create", "tool_execute", "code_analysis",
]
ActionStatus = Literal["pending", "approved", "rejected", "executed"]


@dataclass
class ActionLog:
    id: str
    type: ActionType
    path: str
    status: ActionStatus
    timestamp: datetime
    details: dict = field(default_factory=dict)


class ActionTracker:
    def __init__(self) -> None:
        self._actions: list[ActionLog] = []

    def log(
        self,
        type: ActionType,
        path: str,
        details: dict,
        status: ActionStatus = "pending",
    ) -> ActionLog:
        action = ActionLog(
            id=str(uuid.uuid4()),
            type=type,
            path=path,
            status=status,
            timestamp=datetime.now(),
            details=details,
        )
        self._actions.append(action)
        return action

    def get_actions(self) -> list[ActionLog]:
        return list(self._actions)

    def get_pending_mutations(self) -> list[ActionLog]:
        return [
            a for a in self._actions
            if a.status == "pending" and a.type in (
                "file_create", "file_modify", "file_delete",
                "folder_create", "tool_execute",
            )
        ]

    def update_status(self, action_id: str, status: ActionStatus, approved: bool) -> None:
        for a in self._actions:
            if a.id == action_id:
                a.status = status
                break
