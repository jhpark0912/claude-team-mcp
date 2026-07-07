"""Tests for DB layer: CRUD, optimistic locking, WIP limits, auto notes."""

import json

import pytest

from agent_kanban import db
from agent_kanban.models import (
    CrossProjectError,
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
    VersionConflictError,
    WipLimitExceededError,
)


class TestProjectCRUD:
    def test_init_project(self, conn):
        result = db.init_project(conn, "My Project")
        assert result["name"] == "My Project"
        assert result["id"].startswith("project-")

    def test_get_project(self, conn, project):
        fetched = db.get_project(conn, project["id"])
        assert fetched["name"] == "Test Project"

    def test_get_project_not_found(self, conn):
        with pytest.raises(NotFoundError):
            db.get_project(conn, "nonexistent")


class TestAgentCRUD:
    def test_add_agent(self, conn, project):
        result = db.add_agent(conn, project["id"], "Alice", "PM")
        assert result["name"] == "Alice"
        assert result["role"] == "PM"
        assert result["id"].startswith("agent-")

    def test_add_agent_invalid_project(self, conn):
        with pytest.raises(NotFoundError):
            db.add_agent(conn, "bad-project", "X", "PM")


class TestTaskCRUD:
    def test_create_task_basic(self, conn, project):
        result = db.create_task(conn, project["id"], "Test Task")
        assert result["status"] == "Backlog"
        assert result["version"] == 1
        assert result["assigned_to"] is None

    def test_create_task_with_assignee(self, conn, project, agents):
        result = db.create_task(
            conn, project["id"], "Assigned Task",
            assignee_id=agents["bob"]["id"],
        )
        assert "Bob" in result["assigned_to"]

    def test_create_task_auto_notes(self, conn, project, agents):
        task = db.create_task(
            conn, project["id"], "My Task",
            assignee_id=agents["bob"]["id"],
        )
        detail = db.get_task_detail(conn, task["id"])
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert len(system_notes) >= 2  # created + assigned
        contents = [n["content"] for n in system_notes]
        assert any("Task created" in c for c in contents)
        assert any("Assigned to" in c for c in contents)

    def test_create_task_cross_project(self, conn, project, agents):
        other_project = db.init_project(conn, "Other Project")
        with pytest.raises(CrossProjectError):
            db.create_task(
                conn, other_project["id"], "X",
                assignee_id=agents["bob"]["id"],
            )


class TestUpdateTaskStatus:
    def _make_task(self, conn, project, agents, status_path=None):
        """Helper to create a task and optionally advance it through statuses."""
        task = db.create_task(conn, project["id"], "Status Test",
                              assignee_id=agents["bob"]["id"])
        version = task["version"]
        if status_path:
            for s in status_path:
                result = db.update_task_status(
                    conn, task["id"], s, version, agents["bob"]["id"],
                )
                version = result["version"]
        return task["id"], version

    def test_valid_transition(self, conn, project, agents):
        task_id, v = self._make_task(conn, project, agents)
        result = db.update_task_status(conn, task_id, "Todo", v, agents["bob"]["id"])
        assert result["new_status"] == "Todo"
        assert result["previous_status"] == "Backlog"
        assert result["version"] == v + 1

    def test_invalid_transition(self, conn, project, agents):
        task_id, v = self._make_task(conn, project, agents)
        with pytest.raises(InvalidTransitionError):
            db.update_task_status(conn, task_id, "InProgress", v, agents["bob"]["id"])

    def test_version_conflict(self, conn, project, agents):
        task_id, v = self._make_task(conn, project, agents)
        # First update succeeds
        db.update_task_status(conn, task_id, "Todo", v, agents["bob"]["id"])
        # Same version again fails
        with pytest.raises(VersionConflictError) as exc_info:
            db.update_task_status(conn, task_id, "InProgress", v, agents["bob"]["id"])
        assert exc_info.value.details["current_version"] == v + 1

    def test_comment_creates_progress_note(self, conn, project, agents):
        task_id, v = self._make_task(conn, project, agents)
        db.update_task_status(
            conn, task_id, "Todo", v, agents["bob"]["id"], comment="시작합니다",
        )
        detail = db.get_task_detail(conn, task_id)
        progress_notes = [n for n in detail["notes"] if n["note_type"] == "progress"]
        assert any("시작합니다" in n["content"] for n in progress_notes)

    def test_auto_system_note_on_status_change(self, conn, project, agents):
        task_id, v = self._make_task(conn, project, agents)
        db.update_task_status(conn, task_id, "Todo", v, agents["bob"]["id"])
        detail = db.get_task_detail(conn, task_id)
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert any("Status changed: Backlog → Todo" in n["content"] for n in system_notes)

    def test_full_lifecycle(self, conn, project, agents):
        """Backlog → Todo → InProgress → Review → Done"""
        task_id, v = self._make_task(conn, project, agents)
        for status in ["Todo", "InProgress", "Review", "Done"]:
            result = db.update_task_status(
                conn, task_id, status, v, agents["bob"]["id"],
            )
            v = result["version"]
        assert result["new_status"] == "Done"

    def test_rejected_then_back_to_inprogress(self, conn, project, agents):
        task_id, v = self._make_task(conn, project, agents, ["Todo", "InProgress", "Review"])
        result = db.update_task_status(conn, task_id, "Rejected", v, agents["charlie"]["id"])
        v = result["version"]
        result = db.update_task_status(conn, task_id, "InProgress", v, agents["bob"]["id"])
        assert result["new_status"] == "InProgress"


class TestWipLimits:
    def test_wip_limit_exceeded(self, conn, project, agents):
        # Set WIP limit to 1 for InProgress
        conn.execute(
            "UPDATE projects SET config=? WHERE id=?",
            (json.dumps({"wip_limits": {"InProgress": 1}}), project["id"]),
        )
        conn.commit()

        # Create first task and move to InProgress
        t1 = db.create_task(conn, project["id"], "Task 1", assignee_id=agents["bob"]["id"])
        v1 = t1["version"]
        r1 = db.update_task_status(conn, t1["id"], "Todo", v1, agents["bob"]["id"])
        db.update_task_status(conn, t1["id"], "InProgress", r1["version"], agents["bob"]["id"])

        # Create second task and try to move to InProgress
        t2 = db.create_task(conn, project["id"], "Task 2", assignee_id=agents["bob"]["id"])
        v2 = t2["version"]
        r2 = db.update_task_status(conn, t2["id"], "Todo", v2, agents["bob"]["id"])
        with pytest.raises(WipLimitExceededError):
            db.update_task_status(conn, t2["id"], "InProgress", r2["version"], agents["bob"]["id"])


class TestAssignTask:
    def test_assign_task(self, conn, project, agents):
        task = db.create_task(conn, project["id"], "Assign Test")
        result = db.assign_task(conn, task["id"], agents["bob"]["id"], task["version"])
        assert "Bob" in result["assigned_to"]
        assert result["version"] == task["version"] + 1

    def test_assign_cross_project_error(self, conn, project, agents):
        other_project = db.init_project(conn, "Other")
        other_agent = db.add_agent(conn, other_project["id"], "Outsider", "PM")
        task = db.create_task(conn, project["id"], "X")
        with pytest.raises(CrossProjectError):
            db.assign_task(conn, task["id"], other_agent["id"], task["version"])

    def test_assign_version_conflict(self, conn, project, agents):
        task = db.create_task(conn, project["id"], "X")
        db.assign_task(conn, task["id"], agents["bob"]["id"], task["version"])
        with pytest.raises(VersionConflictError):
            db.assign_task(conn, task["id"], agents["charlie"]["id"], task["version"])


class TestNotes:
    def test_add_note(self, conn, project, agents):
        task = db.create_task(conn, project["id"], "Note Test",
                              assignee_id=agents["bob"]["id"])
        result = db.add_note(conn, task["id"], agents["bob"]["id"],
                             "Progress update", "progress")
        assert "Bob" in result["note"]["agent"]
        assert result["note"]["note_type"] == "progress"

    def test_add_note_cross_project(self, conn, project, agents):
        other_project = db.init_project(conn, "Other")
        other_agent = db.add_agent(conn, other_project["id"], "X", "PM")
        task = db.create_task(conn, project["id"], "X")
        with pytest.raises(CrossProjectError):
            db.add_note(conn, task["id"], other_agent["id"], "X")


class TestFlagBlocker:
    def test_set_blocker(self, conn, project, agents):
        task = db.create_task(conn, project["id"], "Block Test")
        result = db.flag_blocker(conn, task["id"], True, task["version"],
                                 reason="Waiting for API key")
        assert result["is_blocked"] is True
        assert result["blocker_reason"] == "Waiting for API key"
        assert result["version"] == task["version"] + 1

    def test_clear_blocker(self, conn, project, agents):
        task = db.create_task(conn, project["id"], "Block Test")
        r1 = db.flag_blocker(conn, task["id"], True, task["version"],
                              reason="Blocked")
        r2 = db.flag_blocker(conn, task["id"], False, r1["version"])
        assert r2["is_blocked"] is False
        assert r2["blocker_reason"] is None

    def test_set_blocker_without_reason(self, conn, project):
        task = db.create_task(conn, project["id"], "X")
        with pytest.raises(ValidationError):
            db.flag_blocker(conn, task["id"], True, task["version"])

    def test_blocker_auto_notes(self, conn, project, agents):
        task = db.create_task(conn, project["id"], "Block Note Test")
        db.flag_blocker(conn, task["id"], True, task["version"], reason="API down")
        detail = db.get_task_detail(conn, task["id"])
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert any("Blocker set: API down" in n["content"] for n in system_notes)


class TestBoardQueries:
    def test_get_board(self, conn, project, agents):
        db.create_task(conn, project["id"], "T1")
        db.create_task(conn, project["id"], "T2")
        board = db.get_board(conn, project["id"])
        assert board["project"] == "Test Project"
        assert board["counts"]["Backlog"] == 2

    def test_get_task_detail(self, conn, project, agents):
        task = db.create_task(conn, project["id"], "Detail Test",
                              description="Test desc",
                              assignee_id=agents["bob"]["id"])
        detail = db.get_task_detail(conn, task["id"])
        assert detail["title"] == "Detail Test"
        assert detail["description"] == "Test desc"
        assert detail["assigned_to"]["name"] == "Bob"
        assert len(detail["notes"]) >= 1

    def test_get_project_status(self, conn, project, agents):
        db.create_task(conn, project["id"], "T1", assignee_id=agents["bob"]["id"])
        status = db.get_project_status(conn, project["id"])
        assert status["project"] == "Test Project"
        assert len(status["agents"]) == 3
        assert status["summary"]["Backlog"] == 1

    def test_get_board_markdown(self, conn, project, agents):
        db.create_task(conn, project["id"], "MD Test")
        md = db.get_board_markdown(conn, project["id"])
        assert "Test Project" in md
        assert "MD Test" in md

    def test_get_agents_markdown(self, conn, project, agents):
        md = db.get_agents_markdown(conn, project["id"])
        assert "Alice" in md
        assert "Bob" in md
