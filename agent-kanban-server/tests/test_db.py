"""Tests for DB layer: CRUD, optimistic locking, WIP limits, auto notes."""

import json

import pytest

from agent_kanban import db
from agent_kanban.models import (
    CrossTeamError,
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
    VersionConflictError,
    WipLimitExceededError,
)


class TestTeamCRUD:
    def test_create_team(self, conn):
        result = db.create_team(conn, "My Team")
        assert result["name"] == "My Team"
        assert result["id"].startswith("team-")

    def test_get_team(self, conn, team):
        fetched = db.get_team(conn, team["id"])
        assert fetched["name"] == "Test Team"

    def test_get_team_not_found(self, conn):
        with pytest.raises(NotFoundError):
            db.get_team(conn, "nonexistent")


class TestAgentCRUD:
    def test_add_agent(self, conn, team):
        result = db.add_agent(conn, team["id"], "Alice", "PM")
        assert result["name"] == "Alice"
        assert result["role"] == "PM"
        assert result["id"].startswith("agent-")

    def test_add_agent_invalid_team(self, conn):
        with pytest.raises(NotFoundError):
            db.add_agent(conn, "bad-team", "X", "PM")


class TestTaskCRUD:
    def test_create_task_basic(self, conn, team):
        result = db.create_task(conn, team["id"], "Test Task")
        assert result["status"] == "Backlog"
        assert result["version"] == 1
        assert result["assigned_to"] is None

    def test_create_task_with_assignee(self, conn, team, agents):
        result = db.create_task(
            conn, team["id"], "Assigned Task",
            assignee_id=agents["bob"]["id"],
        )
        assert "Bob" in result["assigned_to"]

    def test_create_task_auto_notes(self, conn, team, agents):
        task = db.create_task(
            conn, team["id"], "My Task",
            assignee_id=agents["bob"]["id"],
        )
        detail = db.get_task_detail(conn, task["id"])
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert len(system_notes) >= 2  # created + assigned
        contents = [n["content"] for n in system_notes]
        assert any("Task created" in c for c in contents)
        assert any("Assigned to" in c for c in contents)

    def test_create_task_cross_team(self, conn, team, agents):
        other_team = db.create_team(conn, "Other Team")
        with pytest.raises(CrossTeamError):
            db.create_task(
                conn, other_team["id"], "X",
                assignee_id=agents["bob"]["id"],
            )


class TestUpdateTaskStatus:
    def _make_task(self, conn, team, agents, status_path=None):
        """Helper to create a task and optionally advance it through statuses."""
        task = db.create_task(conn, team["id"], "Status Test",
                              assignee_id=agents["bob"]["id"])
        version = task["version"]
        if status_path:
            for s in status_path:
                result = db.update_task_status(
                    conn, task["id"], s, version, agents["bob"]["id"],
                )
                version = result["version"]
        return task["id"], version

    def test_valid_transition(self, conn, team, agents):
        task_id, v = self._make_task(conn, team, agents)
        result = db.update_task_status(conn, task_id, "Todo", v, agents["bob"]["id"])
        assert result["new_status"] == "Todo"
        assert result["previous_status"] == "Backlog"
        assert result["version"] == v + 1

    def test_invalid_transition(self, conn, team, agents):
        task_id, v = self._make_task(conn, team, agents)
        with pytest.raises(InvalidTransitionError):
            db.update_task_status(conn, task_id, "InProgress", v, agents["bob"]["id"])

    def test_version_conflict(self, conn, team, agents):
        task_id, v = self._make_task(conn, team, agents)
        # First update succeeds
        db.update_task_status(conn, task_id, "Todo", v, agents["bob"]["id"])
        # Same version again fails
        with pytest.raises(VersionConflictError) as exc_info:
            db.update_task_status(conn, task_id, "InProgress", v, agents["bob"]["id"])
        assert exc_info.value.details["current_version"] == v + 1

    def test_comment_creates_progress_note(self, conn, team, agents):
        task_id, v = self._make_task(conn, team, agents)
        db.update_task_status(
            conn, task_id, "Todo", v, agents["bob"]["id"], comment="시작합니다",
        )
        detail = db.get_task_detail(conn, task_id)
        progress_notes = [n for n in detail["notes"] if n["note_type"] == "progress"]
        assert any("시작합니다" in n["content"] for n in progress_notes)

    def test_auto_system_note_on_status_change(self, conn, team, agents):
        task_id, v = self._make_task(conn, team, agents)
        db.update_task_status(conn, task_id, "Todo", v, agents["bob"]["id"])
        detail = db.get_task_detail(conn, task_id)
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert any("Status changed: Backlog → Todo" in n["content"] for n in system_notes)

    def test_full_lifecycle(self, conn, team, agents):
        """Backlog → Todo → InProgress → Review → Done"""
        task_id, v = self._make_task(conn, team, agents)
        for status in ["Todo", "InProgress", "Review", "Done"]:
            result = db.update_task_status(
                conn, task_id, status, v, agents["bob"]["id"],
            )
            v = result["version"]
        assert result["new_status"] == "Done"

    def test_rejected_then_back_to_inprogress(self, conn, team, agents):
        task_id, v = self._make_task(conn, team, agents, ["Todo", "InProgress", "Review"])
        result = db.update_task_status(conn, task_id, "Rejected", v, agents["charlie"]["id"])
        v = result["version"]
        result = db.update_task_status(conn, task_id, "InProgress", v, agents["bob"]["id"])
        assert result["new_status"] == "InProgress"


class TestWipLimits:
    def test_wip_limit_exceeded(self, conn, team, agents):
        # Set WIP limit to 1 for InProgress
        conn.execute(
            "UPDATE teams SET config=? WHERE id=?",
            (json.dumps({"wip_limits": {"InProgress": 1}}), team["id"]),
        )
        conn.commit()

        # Create first task and move to InProgress
        t1 = db.create_task(conn, team["id"], "Task 1", assignee_id=agents["bob"]["id"])
        v1 = t1["version"]
        r1 = db.update_task_status(conn, t1["id"], "Todo", v1, agents["bob"]["id"])
        db.update_task_status(conn, t1["id"], "InProgress", r1["version"], agents["bob"]["id"])

        # Create second task and try to move to InProgress
        t2 = db.create_task(conn, team["id"], "Task 2", assignee_id=agents["bob"]["id"])
        v2 = t2["version"]
        r2 = db.update_task_status(conn, t2["id"], "Todo", v2, agents["bob"]["id"])
        with pytest.raises(WipLimitExceededError):
            db.update_task_status(conn, t2["id"], "InProgress", r2["version"], agents["bob"]["id"])


class TestAssignTask:
    def test_assign_task(self, conn, team, agents):
        task = db.create_task(conn, team["id"], "Assign Test")
        result = db.assign_task(conn, task["id"], agents["bob"]["id"], task["version"])
        assert "Bob" in result["assigned_to"]
        assert result["version"] == task["version"] + 1

    def test_assign_cross_team_error(self, conn, team, agents):
        other_team = db.create_team(conn, "Other")
        other_agent = db.add_agent(conn, other_team["id"], "Outsider", "PM")
        task = db.create_task(conn, team["id"], "X")
        with pytest.raises(CrossTeamError):
            db.assign_task(conn, task["id"], other_agent["id"], task["version"])

    def test_assign_version_conflict(self, conn, team, agents):
        task = db.create_task(conn, team["id"], "X")
        db.assign_task(conn, task["id"], agents["bob"]["id"], task["version"])
        with pytest.raises(VersionConflictError):
            db.assign_task(conn, task["id"], agents["charlie"]["id"], task["version"])


class TestNotes:
    def test_add_note(self, conn, team, agents):
        task = db.create_task(conn, team["id"], "Note Test",
                              assignee_id=agents["bob"]["id"])
        result = db.add_note(conn, task["id"], agents["bob"]["id"],
                             "Progress update", "progress")
        assert "Bob" in result["note"]["agent"]
        assert result["note"]["note_type"] == "progress"

    def test_add_note_cross_team(self, conn, team, agents):
        other_team = db.create_team(conn, "Other")
        other_agent = db.add_agent(conn, other_team["id"], "X", "PM")
        task = db.create_task(conn, team["id"], "X")
        with pytest.raises(CrossTeamError):
            db.add_note(conn, task["id"], other_agent["id"], "X")


class TestFlagBlocker:
    def test_set_blocker(self, conn, team, agents):
        task = db.create_task(conn, team["id"], "Block Test")
        result = db.flag_blocker(conn, task["id"], True, task["version"],
                                 reason="Waiting for API key")
        assert result["is_blocked"] is True
        assert result["blocker_reason"] == "Waiting for API key"
        assert result["version"] == task["version"] + 1

    def test_clear_blocker(self, conn, team, agents):
        task = db.create_task(conn, team["id"], "Block Test")
        r1 = db.flag_blocker(conn, task["id"], True, task["version"],
                              reason="Blocked")
        r2 = db.flag_blocker(conn, task["id"], False, r1["version"])
        assert r2["is_blocked"] is False
        assert r2["blocker_reason"] is None

    def test_set_blocker_without_reason(self, conn, team):
        task = db.create_task(conn, team["id"], "X")
        with pytest.raises(ValidationError):
            db.flag_blocker(conn, task["id"], True, task["version"])

    def test_blocker_auto_notes(self, conn, team, agents):
        task = db.create_task(conn, team["id"], "Block Note Test")
        db.flag_blocker(conn, task["id"], True, task["version"], reason="API down")
        detail = db.get_task_detail(conn, task["id"])
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert any("Blocker set: API down" in n["content"] for n in system_notes)


class TestBoardQueries:
    def test_get_board(self, conn, team, agents):
        db.create_task(conn, team["id"], "T1")
        db.create_task(conn, team["id"], "T2")
        board = db.get_board(conn, team["id"])
        assert board["team"] == "Test Team"
        assert board["counts"]["Backlog"] == 2

    def test_get_task_detail(self, conn, team, agents):
        task = db.create_task(conn, team["id"], "Detail Test",
                              description="Test desc",
                              assignee_id=agents["bob"]["id"])
        detail = db.get_task_detail(conn, task["id"])
        assert detail["title"] == "Detail Test"
        assert detail["description"] == "Test desc"
        assert detail["assigned_to"]["name"] == "Bob"
        assert len(detail["notes"]) >= 1

    def test_get_team_status(self, conn, team, agents):
        db.create_task(conn, team["id"], "T1", assignee_id=agents["bob"]["id"])
        status = db.get_team_status(conn, team["id"])
        assert status["team"] == "Test Team"
        assert len(status["agents"]) == 3
        assert status["summary"]["Backlog"] == 1

    def test_get_board_markdown(self, conn, team, agents):
        db.create_task(conn, team["id"], "MD Test")
        md = db.get_board_markdown(conn, team["id"])
        assert "Test Team" in md
        assert "MD Test" in md

    def test_get_agents_markdown(self, conn, team, agents):
        md = db.get_agents_markdown(conn, team["id"])
        assert "Alice" in md
        assert "Bob" in md
