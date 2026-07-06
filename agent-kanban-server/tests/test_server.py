"""Integration tests for MCP server tools."""

import pytest

from agent_kanban import db
from agent_kanban.server import _get_conn, mcp

# Override DB to use temp for tests
import agent_kanban.server as server_module


@pytest.fixture(autouse=True)
def reset_conn(tmp_path, monkeypatch):
    """Reset the server connection for each test."""
    test_db = tmp_path / "test_server.db"
    monkeypatch.setattr(db, "SQLITE_PATH", test_db)
    conn = db.get_connection()
    db.init_db(conn)
    server_module._conn = conn
    yield conn
    conn.close()
    server_module._conn = None


class TestToolIntegration:
    """Test tools through direct function calls (without MCP transport)."""

    @pytest.mark.asyncio
    async def test_create_team_and_agent(self, reset_conn):
        conn = reset_conn
        team = db.create_team(conn, "Integration Team")
        assert team["id"].startswith("team-")

        agent = db.add_agent(conn, team["id"], "Bot", "Developer")
        assert agent["id"].startswith("agent-")

    @pytest.mark.asyncio
    async def test_full_task_lifecycle(self, reset_conn):
        conn = reset_conn
        team = db.create_team(conn, "Lifecycle Team")
        agent = db.add_agent(conn, team["id"], "Worker", "Developer")

        # Create task
        task = db.create_task(conn, team["id"], "Lifecycle Task",
                              assignee_id=agent["id"])
        assert task["status"] == "Backlog"
        v = task["version"]

        # Backlog → Todo
        r = db.update_task_status(conn, task["id"], "Todo", v, agent["id"])
        v = r["version"]
        assert r["new_status"] == "Todo"

        # Todo → InProgress
        r = db.update_task_status(conn, task["id"], "InProgress", v, agent["id"],
                                  comment="Starting work")
        v = r["version"]
        assert r["new_status"] == "InProgress"

        # Add note
        note = db.add_note(conn, task["id"], agent["id"],
                           "50% complete", "progress")
        assert note["total_notes"] >= 1

        # InProgress → Review
        r = db.update_task_status(conn, task["id"], "Review", v, agent["id"])
        v = r["version"]

        # Review → Done
        r = db.update_task_status(conn, task["id"], "Done", v, agent["id"],
                                  comment="All tests pass")
        assert r["new_status"] == "Done"

        # Verify detail
        detail = db.get_task_detail(conn, task["id"])
        assert detail["status"] == "Done"
        assert len(detail["notes"]) >= 4  # system notes + progress notes

    @pytest.mark.asyncio
    async def test_blocker_workflow(self, reset_conn):
        conn = reset_conn
        team = db.create_team(conn, "Blocker Team")
        agent = db.add_agent(conn, team["id"], "Dev", "Developer")
        task = db.create_task(conn, team["id"], "Blocker Task",
                              assignee_id=agent["id"])

        # Set blocker
        r = db.flag_blocker(conn, task["id"], True, task["version"],
                            reason="Waiting for credentials")
        assert r["is_blocked"] is True
        v = r["version"]

        # Check in board
        board = db.get_board(conn, team["id"])
        blocked_tasks = [t for s in board["board"].values()
                         for t in s if t["is_blocked"]]
        assert len(blocked_tasks) == 1

        # Clear blocker
        r = db.flag_blocker(conn, task["id"], False, v)
        assert r["is_blocked"] is False

    @pytest.mark.asyncio
    async def test_version_conflict_scenario(self, reset_conn):
        """Simulate two agents trying to update the same task."""
        conn = reset_conn
        team = db.create_team(conn, "Conflict Team")
        a1 = db.add_agent(conn, team["id"], "Agent1", "Developer")
        a2 = db.add_agent(conn, team["id"], "Agent2", "Developer")

        task = db.create_task(conn, team["id"], "Shared Task")
        v = task["version"]

        # Agent1 moves to Todo
        r1 = db.update_task_status(conn, task["id"], "Todo", v, a1["id"])

        # Agent2 tries InProgress with stale version (v=1, but current is v=2)
        from agent_kanban.models import VersionConflictError
        with pytest.raises(VersionConflictError):
            db.update_task_status(conn, task["id"], "InProgress", v, a2["id"])

        # Agent2 retries with correct version
        r2 = db.update_task_status(conn, task["id"], "InProgress",
                                   r1["version"], a2["id"])
        assert r2["new_status"] == "InProgress"

    @pytest.mark.asyncio
    async def test_team_status_report(self, reset_conn):
        conn = reset_conn
        team = db.create_team(conn, "Status Team")
        dev = db.add_agent(conn, team["id"], "Dev", "Developer")
        pm = db.add_agent(conn, team["id"], "PM", "PM")

        db.create_task(conn, team["id"], "T1", assignee_id=dev["id"])
        db.create_task(conn, team["id"], "T2", assignee_id=pm["id"])

        status = db.get_team_status(conn, team["id"])
        assert status["summary"]["Backlog"] == 2
        assert len(status["agents"]) == 2
