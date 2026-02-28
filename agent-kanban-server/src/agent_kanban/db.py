"""SQLite database layer with WAL mode, optimistic locking, and auto system notes."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nanoid import generate as nanoid

from .models import (
    ALL_STATUSES,
    CrossTeamError,
    InvalidTransitionError,
    NotFoundError,
    ValidationError,
    VersionConflictError,
    WipLimitExceededError,
    validate_transition,
)

DB_PATH = Path(__file__).parent.parent.parent / "kanban.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    config      TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    team_id     TEXT NOT NULL REFERENCES teams(id),
    name        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'Developer'
                CHECK(role IN ('PM','Developer','Reviewer','Tester','Designer')),
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    team_id     TEXT NOT NULL REFERENCES teams(id),
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'Backlog'
                CHECK(status IN ('Backlog','Todo','InProgress','Review','Done','Rejected')),
    priority    TEXT NOT NULL DEFAULT 'Medium'
                CHECK(priority IN ('Low','Medium','High','Critical')),
    assignee_id TEXT REFERENCES agents(id),
    is_blocked  INTEGER NOT NULL DEFAULT 0,
    blocker_reason TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id    TEXT NOT NULL,
    content     TEXT NOT NULL,
    note_type   TEXT NOT NULL DEFAULT 'progress'
                CHECK(note_type IN ('progress','blocker','handoff','review','system')),
    created_at  TEXT DEFAULT (datetime('now'))
);
"""


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{nanoid(size=8)}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Get a SQLite connection with WAL mode and foreign keys enabled."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables if they don't exist."""
    conn.executescript(SCHEMA)
    conn.commit()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


# ── Helper: agent info ────────────────────────────────────────────────────

def _get_agent_display(conn: sqlite3.Connection, agent_id: str) -> str:
    """Return 'Name (Role)' for display."""
    row = conn.execute("SELECT name, role FROM agents WHERE id=?", (agent_id,)).fetchone()
    if row is None:
        return agent_id
    return f"{row['name']} ({row['role']})"


def _verify_agent_in_team(conn: sqlite3.Connection, agent_id: str, team_id: str) -> None:
    """Verify that the agent belongs to the team."""
    row = conn.execute(
        "SELECT id FROM agents WHERE id=? AND team_id=?", (agent_id, team_id)
    ).fetchone()
    if row is None:
        raise CrossTeamError(agent_id, team_id)


# ── Notes ─────────────────────────────────────────────────────────────────

def _insert_note(
    conn: sqlite3.Connection,
    task_id: str,
    agent_id: str,
    content: str,
    note_type: str = "system",
) -> dict[str, Any]:
    note_id = _gen_id("note")
    now = _now()
    conn.execute(
        "INSERT INTO notes (id, task_id, agent_id, content, note_type, created_at) VALUES (?,?,?,?,?,?)",
        (note_id, task_id, agent_id, content, note_type, now),
    )
    return {"id": note_id, "task_id": task_id, "agent_id": agent_id,
            "content": content, "note_type": note_type, "created_at": now}


# ── Teams ─────────────────────────────────────────────────────────────────

def create_team(conn: sqlite3.Connection, name: str) -> dict[str, Any]:
    team_id = _gen_id("team")
    now = _now()
    conn.execute(
        "INSERT INTO teams (id, name, created_at, config) VALUES (?,?,?,?)",
        (team_id, name, now, "{}"),
    )
    conn.commit()
    return {
        "id": team_id,
        "name": name,
        "created_at": now,
        "message": f"팀 '{name}'이 생성되었습니다.",
    }


def get_team(conn: sqlite3.Connection, team_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM teams WHERE id=?", (team_id,)).fetchone()
    if row is None:
        raise NotFoundError("팀", team_id)
    return _row_to_dict(row)


# ── Agents ────────────────────────────────────────────────────────────────

def add_agent(
    conn: sqlite3.Connection, team_id: str, name: str, role: str
) -> dict[str, Any]:
    get_team(conn, team_id)  # verify team exists
    agent_id = _gen_id("agent")
    now = _now()
    conn.execute(
        "INSERT INTO agents (id, team_id, name, role, created_at) VALUES (?,?,?,?,?)",
        (agent_id, team_id, name, role, now),
    )
    conn.commit()
    return {
        "id": agent_id,
        "team_id": team_id,
        "name": name,
        "role": role,
        "created_at": now,
        "message": f"에이전트 '{name} ({role})'이 팀에 추가되었습니다.",
    }


def get_agent(conn: sqlite3.Connection, agent_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if row is None:
        raise NotFoundError("에이전트", agent_id)
    return _row_to_dict(row)


# ── Tasks ─────────────────────────────────────────────────────────────────

def create_task(
    conn: sqlite3.Connection,
    team_id: str,
    title: str,
    description: str = "",
    priority: str = "Medium",
    assignee_id: str | None = None,
    creator_agent_id: str | None = None,
) -> dict[str, Any]:
    get_team(conn, team_id)  # verify team exists
    task_id = _gen_id("task")
    now = _now()

    if assignee_id:
        _verify_agent_in_team(conn, assignee_id, team_id)

    conn.execute(
        """INSERT INTO tasks (id, team_id, title, description, status, priority,
           assignee_id, is_blocked, blocker_reason, version, created_at, updated_at)
           VALUES (?,?,?,?,?,?,?,0,NULL,1,?,?)""",
        (task_id, team_id, title, description, "Backlog", priority, assignee_id, now, now),
    )

    # Auto system note: task created
    creator_display = "system"
    if creator_agent_id:
        creator_display = _get_agent_display(conn, creator_agent_id)
    elif assignee_id:
        creator_display = _get_agent_display(conn, assignee_id)

    _insert_note(conn, task_id, creator_agent_id or assignee_id or "system",
                 f"Task created by {creator_display}: {title}", "system")

    if assignee_id:
        assignee_display = _get_agent_display(conn, assignee_id)
        _insert_note(conn, task_id, assignee_id or "system",
                     f"Assigned to {assignee_display}", "system")

    conn.commit()

    assigned_to = None
    if assignee_id:
        assigned_to = _get_agent_display(conn, assignee_id)

    return {
        "id": task_id,
        "title": title,
        "status": "Backlog",
        "priority": priority,
        "version": 1,
        "assigned_to": assigned_to,
        "created_at": now,
        "message": f"작업 '{title}'이 Backlog에 추가되었습니다.",
    }


def get_task(conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if row is None:
        raise NotFoundError("작업", task_id)
    return _row_to_dict(row)


def update_task_status(
    conn: sqlite3.Connection,
    task_id: str,
    new_status: str,
    expected_version: int,
    agent_id: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    task = get_task(conn, task_id)

    # 1. Validate transition
    validate_transition(task["status"], new_status)

    # 2. WIP limit check
    team = get_team(conn, task["team_id"])
    config = json.loads(team["config"]) if team["config"] else {}
    wip_limits = config.get("wip_limits", {})
    if new_status in wip_limits:
        current_count = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE team_id=? AND status=?",
            (task["team_id"], new_status),
        ).fetchone()["cnt"]
        if current_count >= wip_limits[new_status]:
            raise WipLimitExceededError(new_status, wip_limits[new_status])

    # 3. Optimistic locking
    now = _now()
    result = conn.execute(
        "UPDATE tasks SET status=?, version=version+1, updated_at=? WHERE id=? AND version=?",
        (new_status, now, task_id, expected_version),
    )
    if result.rowcount == 0:
        current = get_task(conn, task_id)
        raise VersionConflictError(current["version"], current["status"])

    # 4. Auto system note
    agent_display = "system"
    if agent_id:
        agent_display = _get_agent_display(conn, agent_id)
    _insert_note(conn, task_id, agent_id or "system",
                 f"Status changed: {task['status']} → {new_status} by {agent_display}",
                 "system")

    # 5. Comment as progress note
    if comment and agent_id:
        _insert_note(conn, task_id, agent_id, comment, "progress")

    conn.commit()

    updated = get_task(conn, task_id)
    return {
        "task_id": task_id,
        "title": task["title"],
        "previous_status": task["status"],
        "new_status": new_status,
        "version": updated["version"],
        "updated_at": now,
        "message": f"상태가 '{task['status']}' → '{new_status}'로 변경되었습니다.",
    }


def assign_task(
    conn: sqlite3.Connection,
    task_id: str,
    assignee_id: str,
    expected_version: int,
) -> dict[str, Any]:
    task = get_task(conn, task_id)
    _verify_agent_in_team(conn, assignee_id, task["team_id"])

    now = _now()
    result = conn.execute(
        "UPDATE tasks SET assignee_id=?, version=version+1, updated_at=? WHERE id=? AND version=?",
        (assignee_id, now, task_id, expected_version),
    )
    if result.rowcount == 0:
        current = get_task(conn, task_id)
        raise VersionConflictError(current["version"], current["status"])

    assignee_display = _get_agent_display(conn, assignee_id)
    _insert_note(conn, task_id, assignee_id,
                 f"Assigned to {assignee_display}", "system")

    conn.commit()

    updated = get_task(conn, task_id)
    return {
        "task_id": task_id,
        "title": task["title"],
        "assigned_to": assignee_display,
        "version": updated["version"],
        "message": f"작업이 '{assignee_display}'에게 할당되었습니다.",
    }


# ── Notes (public) ────────────────────────────────────────────────────────

def add_note(
    conn: sqlite3.Connection,
    task_id: str,
    agent_id: str,
    content: str,
    note_type: str = "progress",
) -> dict[str, Any]:
    task = get_task(conn, task_id)
    _verify_agent_in_team(conn, agent_id, task["team_id"])

    note = _insert_note(conn, task_id, agent_id, content, note_type)
    conn.commit()

    total = conn.execute(
        "SELECT COUNT(*) as cnt FROM notes WHERE task_id=?", (task_id,)
    ).fetchone()["cnt"]

    agent_display = _get_agent_display(conn, agent_id)
    return {
        "task_id": task_id,
        "note": {
            "id": note["id"],
            "agent": agent_display,
            "content": content,
            "note_type": note_type,
            "created_at": note["created_at"],
        },
        "total_notes": total,
        "message": f"메모가 추가되었습니다. (총 {total}개)",
    }


# ── Blocker ───────────────────────────────────────────────────────────────

def flag_blocker(
    conn: sqlite3.Connection,
    task_id: str,
    is_blocked: bool,
    expected_version: int,
    reason: str | None = None,
) -> dict[str, Any]:
    task = get_task(conn, task_id)

    if is_blocked and not reason:
        raise ValidationError("블로커 설정 시 reason은 필수입니다.")

    now = _now()
    blocker_reason = reason if is_blocked else None
    result = conn.execute(
        "UPDATE tasks SET is_blocked=?, blocker_reason=?, version=version+1, updated_at=? WHERE id=? AND version=?",
        (1 if is_blocked else 0, blocker_reason, now, task_id, expected_version),
    )
    if result.rowcount == 0:
        current = get_task(conn, task_id)
        raise VersionConflictError(current["version"], current["status"])

    # Auto system note
    if is_blocked:
        _insert_note(conn, task_id, "system", f"Blocker set: {reason}", "system")
        _insert_note(conn, task_id, "system", reason, "blocker")
    else:
        _insert_note(conn, task_id, "system", "Blocker resolved", "system")

    conn.commit()

    updated = get_task(conn, task_id)
    if is_blocked:
        msg = f"블로커가 설정되었습니다: '{reason}'"
    else:
        msg = "블로커가 해제되었습니다."

    return {
        "task_id": task_id,
        "title": task["title"],
        "is_blocked": is_blocked,
        "blocker_reason": blocker_reason,
        "version": updated["version"],
        "message": msg,
    }


# ── Board Queries ─────────────────────────────────────────────────────────

def get_board(conn: sqlite3.Connection, team_id: str) -> dict[str, Any]:
    team = get_team(conn, team_id)

    board: dict[str, list] = {s: [] for s in ALL_STATUSES}
    counts: dict[str, int] = {s: 0 for s in ALL_STATUSES}

    tasks = conn.execute(
        "SELECT * FROM tasks WHERE team_id=? ORDER BY priority DESC, created_at ASC",
        (team_id,),
    ).fetchall()

    for t in tasks:
        t = dict(t)
        status = t["status"]
        counts[status] = counts.get(status, 0) + 1

        assigned_to = None
        if t["assignee_id"]:
            assigned_to = _get_agent_display(conn, t["assignee_id"])

        # Get latest note
        latest = conn.execute(
            "SELECT content FROM notes WHERE task_id=? AND note_type != 'system' ORDER BY created_at DESC LIMIT 1",
            (t["id"],),
        ).fetchone()

        entry: dict[str, Any] = {
            "id": t["id"],
            "title": t["title"],
            "priority": t["priority"],
            "assigned_to": assigned_to,
            "is_blocked": bool(t["is_blocked"]),
            "version": t["version"],
        }
        if latest:
            entry["latest_note"] = latest["content"]

        board[status].append(entry)

    config = json.loads(team["config"]) if team["config"] else {}
    wip_limits = config.get("wip_limits", {})
    wip_status = {}
    for s, limit in wip_limits.items():
        wip_status[s] = f"{counts.get(s, 0)}/{limit}"

    return {
        "team": team["name"],
        "counts": counts,
        "board": board,
        "wip_status": wip_status,
        "updated_at": _now(),
    }


def get_task_detail(conn: sqlite3.Connection, task_id: str) -> dict[str, Any]:
    task = get_task(conn, task_id)
    team = get_team(conn, task["team_id"])

    assigned_to = None
    if task["assignee_id"]:
        agent = get_agent(conn, task["assignee_id"])
        assigned_to = {"id": agent["id"], "name": agent["name"], "role": agent["role"]}

    notes_rows = conn.execute(
        "SELECT * FROM notes WHERE task_id=? ORDER BY created_at ASC",
        (task_id,),
    ).fetchall()

    notes = []
    for n in notes_rows:
        n = dict(n)
        agent_display = "system"
        if n["agent_id"] != "system":
            try:
                agent_display = _get_agent_display(conn, n["agent_id"])
            except Exception:
                agent_display = n["agent_id"]
        notes.append({
            "id": n["id"],
            "agent": agent_display,
            "content": n["content"],
            "note_type": n["note_type"],
            "created_at": n["created_at"],
        })

    return {
        "id": task["id"],
        "title": task["title"],
        "description": task["description"],
        "status": task["status"],
        "priority": task["priority"],
        "is_blocked": bool(task["is_blocked"]),
        "blocker_reason": task["blocker_reason"],
        "version": task["version"],
        "assigned_to": assigned_to,
        "team": {"id": team["id"], "name": team["name"]},
        "notes": notes,
        "created_at": task["created_at"],
        "updated_at": task["updated_at"],
    }


def get_team_status(
    conn: sqlite3.Connection, team_id: str, activity_hours: int = 24
) -> dict[str, Any]:
    team = get_team(conn, team_id)

    # Summary counts
    summary = {s: 0 for s in ALL_STATUSES}
    rows = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM tasks WHERE team_id=? GROUP BY status",
        (team_id,),
    ).fetchall()
    for r in rows:
        summary[r["status"]] = r["cnt"]

    # Agent workloads
    agents_rows = conn.execute(
        "SELECT * FROM agents WHERE team_id=?", (team_id,)
    ).fetchall()

    agents = []
    for a in agents_rows:
        a = dict(a)
        in_progress = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE assignee_id=? AND status='InProgress'",
            (a["id"],),
        ).fetchone()["cnt"]
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE assignee_id=?",
            (a["id"],),
        ).fetchone()["cnt"]
        agents.append({
            "name": a["name"],
            "role": a["role"],
            "in_progress": in_progress,
            "total": total,
        })

    # Blockers
    blocker_rows = conn.execute(
        "SELECT * FROM tasks WHERE team_id=? AND is_blocked=1",
        (team_id,),
    ).fetchall()
    blockers = []
    for b in blocker_rows:
        b = dict(b)
        assigned_to = None
        if b["assignee_id"]:
            assigned_to = _get_agent_display(conn, b["assignee_id"])
        blockers.append({
            "task_id": b["id"],
            "title": b["title"],
            "reason": b["blocker_reason"],
            "assigned_to": assigned_to,
        })

    # Recent activity (from notes)
    recent_notes = conn.execute(
        """SELECT n.*, t.title as task_title
           FROM notes n JOIN tasks t ON n.task_id = t.id
           WHERE t.team_id=? AND n.note_type='system'
           AND n.created_at >= datetime('now', ?)
           ORDER BY n.created_at DESC LIMIT 20""",
        (team_id, f"-{activity_hours} hours"),
    ).fetchall()

    recent_activity = []
    for rn in recent_notes:
        rn = dict(rn)
        agent_name = "system"
        if rn["agent_id"] != "system":
            try:
                agent_name = _get_agent_display(conn, rn["agent_id"]).split(" (")[0]
            except Exception:
                agent_name = rn["agent_id"]
        recent_activity.append({
            "agent": agent_name,
            "action": "status_change" if "Status changed" in rn["content"] else "update",
            "task": rn["task_title"],
            "detail": rn["content"],
            "at": rn["created_at"],
        })

    return {
        "team": team["name"],
        "summary": summary,
        "agents": agents,
        "blockers": blockers,
        "recent_activity": recent_activity,
    }


# ── Board Markdown (for Resources) ───────────────────────────────────────

def get_board_markdown(conn: sqlite3.Connection, team_id: str) -> str:
    data = get_board(conn, team_id)
    lines = [f"# {data['team']} - Kanban Board\n"]

    for status in ALL_STATUSES:
        tasks = data["board"][status]
        count = data["counts"][status]
        wip_info = ""
        if status in data["wip_status"]:
            wip_info = f" [WIP: {data['wip_status'][status]}]"

        lines.append(f"## {status} ({count}){wip_info}")

        if not tasks:
            lines.append("_없음_\n")
            continue

        has_notes = any("latest_note" in t for t in tasks)
        if has_notes:
            lines.append("| ID | 작업 | 우선순위 | 담당자 | 최근 메모 | v |")
            lines.append("|----|------|---------|--------|----------|---|")
            for t in tasks:
                note = t.get("latest_note", "")
                blocked = " **[BLOCKED]**" if t["is_blocked"] else ""
                lines.append(
                    f"| {t['id']} | {t['title']}{blocked} | {t['priority']} "
                    f"| {t['assigned_to'] or '-'} | {note} | {t['version']} |"
                )
        else:
            lines.append("| ID | 작업 | 우선순위 | 담당자 | v |")
            lines.append("|----|------|---------|--------|---|")
            for t in tasks:
                blocked = " **[BLOCKED]**" if t["is_blocked"] else ""
                lines.append(
                    f"| {t['id']} | {t['title']}{blocked} | {t['priority']} "
                    f"| {t['assigned_to'] or '-'} | {t['version']} |"
                )
        lines.append("")

    lines.append(f"최종 업데이트: {data['updated_at']}")
    return "\n".join(lines)


def get_agents_markdown(conn: sqlite3.Connection, team_id: str) -> str:
    team = get_team(conn, team_id)
    agents_rows = conn.execute(
        "SELECT * FROM agents WHERE team_id=?", (team_id,)
    ).fetchall()

    lines = [f"# {team['name']} - Agents\n"]
    lines.append("| 에이전트 | 역할 | 진행 중 | 전체 | 블로커 |")
    lines.append("|---------|------|---------|------|--------|")

    for a in agents_rows:
        a = dict(a)
        in_progress = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE assignee_id=? AND status='InProgress'",
            (a["id"],),
        ).fetchone()["cnt"]
        total = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE assignee_id=?",
            (a["id"],),
        ).fetchone()["cnt"]
        blockers = conn.execute(
            "SELECT COUNT(*) as cnt FROM tasks WHERE assignee_id=? AND is_blocked=1",
            (a["id"],),
        ).fetchone()["cnt"]
        lines.append(
            f"| {a['name']} | {a['role']} | {in_progress} | {total} | {blockers} |"
        )

    return "\n".join(lines)
