"""Tests for models: state transitions, enums, exceptions."""

import pytest

from agent_kanban.models import (
    ALL_STATUSES,
    VALID_TRANSITIONS,
    AgentRole,
    InvalidTransitionError,
    NoteType,
    Priority,
    TaskStatus,
    ValidationError,
    VersionConflictError,
    WipLimitExceededError,
    validate_transition,
)


class TestEnums:
    def test_task_status_values(self):
        assert TaskStatus.BACKLOG.value == "Backlog"
        assert TaskStatus.IN_PROGRESS.value == "InProgress"
        assert TaskStatus.DONE.value == "Done"

    def test_priority_values(self):
        assert Priority.LOW.value == "Low"
        assert Priority.CRITICAL.value == "Critical"

    def test_agent_role_values(self):
        assert AgentRole.PM.value == "PM"
        assert AgentRole.DEVELOPER.value == "Developer"

    def test_note_type_values(self):
        assert NoteType.PROGRESS.value == "progress"
        assert NoteType.SYSTEM.value == "system"

    def test_all_statuses_complete(self):
        assert len(ALL_STATUSES) == 6
        for s in ALL_STATUSES:
            assert s in VALID_TRANSITIONS


class TestStateTransitions:
    """Test VALID_TRANSITIONS matrix."""

    def test_backlog_to_todo(self):
        validate_transition("Backlog", "Todo")  # should not raise

    def test_backlog_to_inprogress_forbidden(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            validate_transition("Backlog", "InProgress")
        assert exc_info.value.error_code == "INVALID_TRANSITION"
        assert "Todo" in exc_info.value.details["allowed_transitions"]

    def test_todo_to_backlog(self):
        validate_transition("Todo", "Backlog")

    def test_todo_to_inprogress(self):
        validate_transition("Todo", "InProgress")

    def test_todo_to_rejected(self):
        validate_transition("Todo", "Rejected")

    def test_inprogress_to_review(self):
        validate_transition("InProgress", "Review")

    def test_inprogress_to_done(self):
        validate_transition("InProgress", "Done")

    def test_inprogress_to_rejected(self):
        validate_transition("InProgress", "Rejected")

    def test_inprogress_to_backlog_forbidden(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition("InProgress", "Backlog")

    def test_review_to_done(self):
        validate_transition("Review", "Done")

    def test_review_to_rejected(self):
        validate_transition("Review", "Rejected")

    def test_done_no_transitions(self):
        for target in ALL_STATUSES:
            if target != "Done":
                with pytest.raises(InvalidTransitionError):
                    validate_transition("Done", target)

    def test_rejected_to_inprogress(self):
        validate_transition("Rejected", "InProgress")

    def test_rejected_to_done_forbidden(self):
        with pytest.raises(InvalidTransitionError):
            validate_transition("Rejected", "Done")


class TestExceptions:
    def test_invalid_transition_error_to_dict(self):
        e = InvalidTransitionError("Done", "Backlog", [])
        d = e.to_dict()
        assert d["error"] == "INVALID_TRANSITION"
        assert d["current_status"] == "Done"
        assert d["allowed_transitions"] == []

    def test_version_conflict_error_to_dict(self):
        e = VersionConflictError(3, "Review")
        d = e.to_dict()
        assert d["error"] == "VERSION_CONFLICT"
        assert d["current_version"] == 3

    def test_wip_limit_exceeded_to_dict(self):
        e = WipLimitExceededError("InProgress", 3)
        d = e.to_dict()
        assert d["error"] == "WIP_LIMIT_EXCEEDED"
        assert d["wip_limit"] == 3

    def test_validation_error_to_dict(self):
        e = ValidationError("reason is required")
        d = e.to_dict()
        assert d["error"] == "VALIDATION_ERROR"
