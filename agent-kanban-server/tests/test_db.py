"""Tests for DB layer: CRUD, optimistic locking, WIP limits, auto notes."""

import json

import pytest

from agent_kanban import db
from agent_kanban.models import (
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


class TestTaskCRUD:
    def test_create_task_basic(self, conn, project):
        result = db.create_task(conn, project["id"], "Test Task")
        assert result["status"] == "Backlog"
        assert result["version"] == 1

    def test_create_task_auto_notes(self, conn, project):
        task = db.create_task(conn, project["id"], "My Task")
        detail = db.get_task_detail(conn, task["id"])
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert len(system_notes) >= 1
        contents = [n["content"] for n in system_notes]
        assert any("Task created" in c for c in contents)


class TestUpdateTaskStatus:
    def _make_task(self, conn, project, status_path=None):
        """Helper to create a task and optionally advance it through statuses."""
        task = db.create_task(conn, project["id"], "Status Test")
        version = task["version"]
        if status_path:
            for s in status_path:
                result = db.update_task_status(conn, task["id"], s, version)
                version = result["version"]
        return task["id"], version

    def test_valid_transition(self, conn, project):
        task_id, v = self._make_task(conn, project)
        result = db.update_task_status(conn, task_id, "Todo", v)
        assert result["new_status"] == "Todo"
        assert result["previous_status"] == "Backlog"
        assert result["version"] == v + 1

    def test_invalid_transition(self, conn, project):
        task_id, v = self._make_task(conn, project)
        with pytest.raises(InvalidTransitionError):
            db.update_task_status(conn, task_id, "InProgress", v)

    def test_version_conflict(self, conn, project):
        task_id, v = self._make_task(conn, project)
        db.update_task_status(conn, task_id, "Todo", v)
        with pytest.raises(VersionConflictError) as exc_info:
            db.update_task_status(conn, task_id, "InProgress", v)
        assert exc_info.value.details["current_version"] == v + 1

    def test_comment_creates_progress_note(self, conn, project):
        task_id, v = self._make_task(conn, project)
        db.update_task_status(conn, task_id, "Todo", v, comment="시작합니다")
        detail = db.get_task_detail(conn, task_id)
        progress_notes = [n for n in detail["notes"] if n["note_type"] == "progress"]
        assert any("시작합니다" in n["content"] for n in progress_notes)

    def test_auto_system_note_on_status_change(self, conn, project):
        task_id, v = self._make_task(conn, project)
        db.update_task_status(conn, task_id, "Todo", v)
        detail = db.get_task_detail(conn, task_id)
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert any("Status changed: Backlog → Todo" in n["content"] for n in system_notes)

    def test_full_lifecycle(self, conn, project):
        """Backlog → Todo → InProgress → Review → Done"""
        task_id, v = self._make_task(conn, project)
        for status in ["Todo", "InProgress", "Review", "Done"]:
            result = db.update_task_status(conn, task_id, status, v)
            v = result["version"]
        assert result["new_status"] == "Done"

    def test_rejected_then_back_to_inprogress(self, conn, project):
        task_id, v = self._make_task(conn, project, ["Todo", "InProgress", "Review"])
        result = db.update_task_status(conn, task_id, "Rejected", v)
        v = result["version"]
        result = db.update_task_status(conn, task_id, "InProgress", v)
        assert result["new_status"] == "InProgress"


class TestWipLimits:
    def test_wip_limit_exceeded(self, conn, project):
        conn.execute(
            "UPDATE projects SET config=? WHERE id=?",
            (json.dumps({"wip_limits": {"InProgress": 1}}), project["id"]),
        )
        conn.commit()

        t1 = db.create_task(conn, project["id"], "Task 1")
        v1 = t1["version"]
        r1 = db.update_task_status(conn, t1["id"], "Todo", v1)
        db.update_task_status(conn, t1["id"], "InProgress", r1["version"])

        t2 = db.create_task(conn, project["id"], "Task 2")
        v2 = t2["version"]
        r2 = db.update_task_status(conn, t2["id"], "Todo", v2)
        with pytest.raises(WipLimitExceededError):
            db.update_task_status(conn, t2["id"], "InProgress", r2["version"])


class TestNotes:
    def test_add_note(self, conn, project):
        task = db.create_task(conn, project["id"], "Note Test")
        result = db.add_note(conn, task["id"], "Progress update", "progress")
        assert result["note"]["note_type"] == "progress"
        assert result["note"]["content"] == "Progress update"


class TestFlagBlocker:
    def test_set_blocker(self, conn, project):
        task = db.create_task(conn, project["id"], "Block Test")
        result = db.flag_blocker(conn, task["id"], True, task["version"],
                                 reason="Waiting for API key")
        assert result["is_blocked"] is True
        assert result["blocker_reason"] == "Waiting for API key"
        assert result["version"] == task["version"] + 1

    def test_clear_blocker(self, conn, project):
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

    def test_blocker_auto_notes(self, conn, project):
        task = db.create_task(conn, project["id"], "Block Note Test")
        db.flag_blocker(conn, task["id"], True, task["version"], reason="API down")
        detail = db.get_task_detail(conn, task["id"])
        system_notes = [n for n in detail["notes"] if n["note_type"] == "system"]
        assert any("Blocker set: API down" in n["content"] for n in system_notes)


class TestBoardQueries:
    def test_get_board(self, conn, project):
        db.create_task(conn, project["id"], "T1")
        db.create_task(conn, project["id"], "T2")
        board = db.get_board(conn, project["id"])
        assert board["project"] == "Test Project"
        assert board["counts"]["Backlog"] == 2

    def test_get_task_detail(self, conn, project):
        task = db.create_task(conn, project["id"], "Detail Test",
                              description="Test desc")
        detail = db.get_task_detail(conn, task["id"])
        assert detail["title"] == "Detail Test"
        assert detail["description"] == "Test desc"
        assert len(detail["notes"]) >= 1

    def test_get_project_status(self, conn, project):
        db.create_task(conn, project["id"], "T1")
        status = db.get_project_status(conn, project["id"])
        assert status["project"] == "Test Project"
        assert status["summary"]["Backlog"] == 1

    def test_get_board_markdown(self, conn, project):
        db.create_task(conn, project["id"], "MD Test")
        md = db.get_board_markdown(conn, project["id"])
        assert "Test Project" in md
        assert "MD Test" in md
