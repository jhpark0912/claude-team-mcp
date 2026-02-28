"""Pydantic models, Enums, state machine, and custom exceptions."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    BACKLOG = "Backlog"
    TODO = "Todo"
    IN_PROGRESS = "InProgress"
    REVIEW = "Review"
    DONE = "Done"
    REJECTED = "Rejected"


class Priority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class AgentRole(str, Enum):
    PM = "PM"
    DEVELOPER = "Developer"
    REVIEWER = "Reviewer"
    TESTER = "Tester"
    DESIGNER = "Designer"


class NoteType(str, Enum):
    PROGRESS = "progress"
    BLOCKER = "blocker"
    HANDOFF = "handoff"
    REVIEW = "review"
    SYSTEM = "system"


# ── State Machine ──────────────────────────────────────────────────────────

VALID_TRANSITIONS: dict[str, list[str]] = {
    "Backlog": ["Todo"],
    "Todo": ["Backlog", "InProgress"],
    "InProgress": ["Review", "Done"],
    "Review": ["Done", "Rejected"],
    "Done": [],
    "Rejected": ["InProgress"],
}

ALL_STATUSES = ["Backlog", "Todo", "InProgress", "Review", "Done", "Rejected"]


def validate_transition(current: str, new: str) -> None:
    """Validate that a status transition is allowed."""
    allowed = VALID_TRANSITIONS.get(current, [])
    if new not in allowed:
        raise InvalidTransitionError(current, new, allowed)


# ── Pydantic Models ───────────────────────────────────────────────────────

class TeamModel(BaseModel):
    id: str
    name: str
    created_at: str
    config: dict[str, Any] = Field(default_factory=dict)


class AgentModel(BaseModel):
    id: str
    team_id: str
    name: str
    role: str
    created_at: str


class TaskModel(BaseModel):
    id: str
    team_id: str
    title: str
    description: str = ""
    status: str = "Backlog"
    priority: str = "Medium"
    assignee_id: str | None = None
    is_blocked: bool = False
    blocker_reason: str | None = None
    version: int = 1
    created_at: str
    updated_at: str


class NoteModel(BaseModel):
    id: str
    task_id: str
    agent_id: str
    content: str
    note_type: str = "progress"
    created_at: str


# ── Custom Exceptions ─────────────────────────────────────────────────────

class KanbanError(Exception):
    """Base exception for kanban errors."""

    def __init__(self, error_code: str, message: str, details: dict[str, Any] | None = None):
        self.error_code = error_code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {"error": self.error_code, "message": self.message, **self.details}


class InvalidTransitionError(KanbanError):
    def __init__(self, current: str, new: str, allowed: list[str]):
        super().__init__(
            error_code="INVALID_TRANSITION",
            message=f"'{current}' → '{new}' 전이는 허용되지 않습니다.",
            details={
                "current_status": current,
                "requested_status": new,
                "allowed_transitions": allowed,
            },
        )


class VersionConflictError(KanbanError):
    def __init__(self, current_version: int, current_status: str):
        super().__init__(
            error_code="VERSION_CONFLICT",
            message="다른 에이전트가 이미 수정했습니다. get_task_detail로 최신 상태 조회 후 재시도하세요.",
            details={
                "current_version": current_version,
                "current_status": current_status,
            },
        )


class WipLimitExceededError(KanbanError):
    def __init__(self, status: str, limit: int):
        super().__init__(
            error_code="WIP_LIMIT_EXCEEDED",
            message=f"'{status}' 상태의 WIP 제한({limit})을 초과했습니다. 다른 작업을 먼저 완료하세요.",
            details={"status": status, "wip_limit": limit},
        )


class CrossTeamError(KanbanError):
    def __init__(self, agent_id: str, team_id: str):
        super().__init__(
            error_code="CROSS_TEAM_ERROR",
            message=f"에이전트 '{agent_id}'는 팀 '{team_id}'에 소속되지 않았습니다.",
            details={"agent_id": agent_id, "team_id": team_id},
        )


class NotFoundError(KanbanError):
    def __init__(self, entity: str, entity_id: str):
        super().__init__(
            error_code="NOT_FOUND",
            message=f"{entity} '{entity_id}'를 찾을 수 없습니다.",
            details={"entity": entity, "id": entity_id},
        )


class ValidationError(KanbanError):
    def __init__(self, message: str):
        super().__init__(
            error_code="VALIDATION_ERROR",
            message=message,
        )
