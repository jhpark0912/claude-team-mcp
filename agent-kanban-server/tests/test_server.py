"""Integration tests for MCP server tools."""

import pytest

from agent_kanban import db
from agent_kanban.server import _get_conn, mcp

import agent_kanban.server as server_module


@pytest.fixture(autouse=True)
def reset_conn(tmp_path, monkeypatch):
    """Reset the server connection for each test."""
    test_db = tmp_path / "test_server.db"
    monkeypatch.setattr(db, "SQLITE_PATH", test_db)
    conn = db.get_connection()
    db.init_db(conn)
    db.migrate_db(conn)
    server_module._conn = conn
    yield conn
    conn.close()
    server_module._conn = None


class TestToolIntegration:
    """Test tools through direct function calls (without MCP transport)."""

    @pytest.mark.asyncio
    async def test_init_project(self, reset_conn):
        conn = reset_conn
        project = db.init_project(conn, "Integration Project")
        assert project["id"].startswith("project-")

    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self, reset_conn):
        conn = reset_conn
        project = db.init_project(conn, "Lifecycle Project")

        # Create task
        task = db.create_task(conn, project["id"], "Lifecycle Task")
        assert task["status"] == "Backlog"
        v = task["version"]

        # Backlog → Todo
        r = db.update_task_status(conn, task["id"], "Todo", v)
        v = r["version"]
        assert r["new_status"] == "Todo"

        # Todo → InProgress
        r = db.update_task_status(conn, task["id"], "InProgress", v,
                                  comment="Starting work")
        v = r["version"]
        assert r["new_status"] == "InProgress"

        # Add note
        note = db.add_note(conn, task["id"], "50% complete", "progress")
        assert note["total_notes"] >= 1

        # InProgress → Review
        r = db.update_task_status(conn, task["id"], "Review", v)
        v = r["version"]

        # Review → Done
        r = db.update_task_status(conn, task["id"], "Done", v,
                                  comment="All tests pass")
        assert r["new_status"] == "Done"

        # Verify detail
        detail = db.get_task_detail(conn, task["id"])
        assert detail["status"] == "Done"
        assert len(detail["notes"]) >= 4  # system notes + progress notes

    @pytest.mark.asyncio
    async def test_blocker_workflow(self, reset_conn):
        conn = reset_conn
        project = db.init_project(conn, "Blocker Project")
        task = db.create_task(conn, project["id"], "Blocker Task")

        # Set blocker
        r = db.flag_blocker(conn, task["id"], True, task["version"],
                            reason="Waiting for credentials")
        assert r["is_blocked"] is True
        v = r["version"]

        # Check in board
        board = db.get_board(conn, project["id"])
        blocked_tasks = [t for s in board["board"].values()
                         for t in s if t["is_blocked"]]
        assert len(blocked_tasks) == 1

        # Clear blocker
        r = db.flag_blocker(conn, task["id"], False, v)
        assert r["is_blocked"] is False

    @pytest.mark.asyncio
    async def test_version_conflict_scenario(self, reset_conn):
        """Simulate two sessions trying to update the same task."""
        conn = reset_conn
        project = db.init_project(conn, "Conflict Project")

        task = db.create_task(conn, project["id"], "Shared Task")
        v = task["version"]

        # Session 1 moves to Todo
        r1 = db.update_task_status(conn, task["id"], "Todo", v)

        # Session 2 tries with stale version
        from agent_kanban.models import VersionConflictError
        with pytest.raises(VersionConflictError):
            db.update_task_status(conn, task["id"], "InProgress", v)

        # Session 2 retries with correct version
        r2 = db.update_task_status(conn, task["id"], "InProgress", r1["version"])
        assert r2["new_status"] == "InProgress"

    @pytest.mark.asyncio
    async def test_project_status_report(self, reset_conn):
        conn = reset_conn
        project = db.init_project(conn, "Status Project")

        db.create_task(conn, project["id"], "T1")
        db.create_task(conn, project["id"], "T2")

        status = db.get_project_status(conn, project["id"])
        assert status["summary"]["Backlog"] == 2
