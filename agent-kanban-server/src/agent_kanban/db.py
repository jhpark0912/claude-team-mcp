"""Database layer — SQLite(로컬) / PostgreSQL(클라우드) 듀얼 모드 지원.

KANBAN_DB_HOST 환경변수 설정 여부로 자동 분기:
  - 미설정 → SQLite (로컬, 기본값)
  - 설정   → PostgreSQL (클라우드 공유 DB)
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from nanoid import generate as nanoid

from .models import (
    ALL_STATUSES,
    NoteType,
    NotFoundError,
    Priority,
    ValidationError,
    VersionConflictError,
    WipLimitExceededError,
    validate_transition,
)

load_dotenv(Path(__file__).parent.parent.parent / ".env")

# ── DB 설정 ────────────────────────────────────────────────────────────────

_env_db_path = os.environ.get("KANBAN_DB_PATH")
SQLITE_PATH = Path(_env_db_path) if _env_db_path else Path(__file__).parent.parent.parent / "kanban.db"

PG_CONFIG = {
    "host": os.environ.get("KANBAN_DB_HOST", ""),
    "port": int(os.environ.get("KANBAN_DB_PORT", "5432")),
    "user": os.environ.get("KANBAN_DB_USER", "ai_board_user"),
    "password": os.environ.get("KANBAN_DB_PASSWORD", ""),
    "dbname": os.environ.get("KANBAN_DB_NAME", "ai_board"),
}


def _use_pg() -> bool:
    return bool(os.environ.get("KANBAN_DB_HOST"))


# ── 스키마 ─────────────────────────────────────────────────────────────────

SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    config      TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id),
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'Backlog'
                CHECK(status IN ('Backlog','Todo','InProgress','Review','Done','Rejected')),
    priority    TEXT NOT NULL DEFAULT 'Medium'
                CHECK(priority IN ('Low','Medium','High','Critical')),
    is_blocked  INTEGER NOT NULL DEFAULT 0,
    blocker_reason TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    note_type   TEXT NOT NULL DEFAULT 'progress'
                CHECK(note_type IN ('progress','blocker','handoff','review','system')),
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status);
CREATE INDEX IF NOT EXISTS idx_notes_task_type_created ON notes(task_id, note_type, created_at DESC);
"""

PG_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    config      TEXT DEFAULT '{}'
)""",
    """CREATE TABLE IF NOT EXISTS tasks (
    id          TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL REFERENCES projects(id),
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'Backlog'
                CHECK(status IN ('Backlog','Todo','InProgress','Review','Done','Rejected')),
    priority    TEXT NOT NULL DEFAULT 'Medium'
                CHECK(priority IN ('Low','Medium','High','Critical')),
    is_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
    blocker_reason TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
)""",
    """CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    note_type   TEXT NOT NULL DEFAULT 'progress'
                CHECK(note_type IN ('progress','blocker','handoff','review','system')),
    created_at  TIMESTAMP DEFAULT NOW()
)""",
    "CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_notes_task_type_created ON notes(task_id, note_type, created_at DESC)",
)


# ── 연결 & 헬퍼 ───────────────────────────────────────────────────────────

_pg_pool = None


def _get_pg_pool():
    """PostgreSQL 커넥션 풀 (싱글턴). 최소 1, 최대 5 커넥션."""
    global _pg_pool
    if _pg_pool is None:
        from psycopg2.pool import ThreadedConnectionPool
        _pg_pool = ThreadedConnectionPool(1, 5, **PG_CONFIG)
    return _pg_pool


def get_connection():
    """KANBAN_DB_HOST 설정 여부에 따라 PostgreSQL 또는 SQLite 연결 반환."""
    if _use_pg():
        import psycopg2
        return psycopg2.connect(**PG_CONFIG)
    else:
        conn = sqlite3.connect(str(SQLITE_PATH))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn


def get_pooled_connection():
    """풀에서 PostgreSQL 커넥션 획득. SQLite면 일반 연결 반환."""
    if _use_pg():
        return _get_pg_pool().getconn()
    else:
        return get_connection()


def return_pooled_connection(conn):
    """풀에 PostgreSQL 커넥션 반환. SQLite면 close."""
    if _use_pg():
        _get_pg_pool().putconn(conn)
    else:
        conn.close()


def _is_pg(conn) -> bool:
    try:
        import psycopg2.extensions
        return isinstance(conn, psycopg2.extensions.connection)
    except ImportError:
        return False


def _exec(conn, sql: str, params: tuple = ()):
    """PostgreSQL / SQLite 공용 실행 헬퍼.
    - PostgreSQL: %s 플레이스홀더, RealDictCursor
    - SQLite: %s → ? 자동 변환, 기본 커서
    """
    if _is_pg(conn):
        from psycopg2.extras import RealDictCursor
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(sql, params)
        return cur
    else:
        sqlite_sql = sql.replace("%s", "?")
        return conn.execute(sqlite_sql, params)


def init_db(conn) -> None:
    """테이블 생성 (없을 경우)."""
    # 레거시(teams/team_id) → projects/project_id rename. CREATE 전에 실행해야
    # 빈 projects 테이블이 먼저 생기는 것을 막는다.
    _migrate_legacy_team_to_project(conn)
    # 레거시 agents 테이블이 남아있으면 FK 충돌 발생 — 스키마 생성 전에 제거
    _drop_legacy_agents(conn)
    if _is_pg(conn):
        for stmt in PG_SCHEMA:
            _exec(conn, stmt)
    else:
        conn.executescript(SQLITE_SCHEMA)
    conn.commit()


def _table_exists(conn, table: str) -> bool:
    if _is_pg(conn):
        row = _exec(
            conn, "SELECT 1 FROM information_schema.tables WHERE table_name=%s", (table,)
        ).fetchone()
        return row is not None
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _migrate_legacy_team_to_project(conn) -> None:
    """레거시 스키마(teams/team_id)를 projects/project_id로 rename (멱등).

    기존 kanban.db에만 1회 적용된다. projects가 이미 있거나 teams가 없으면 no-op.
    데이터 삭제 없이 테이블·컬럼 이름만 바꾼다. (SQLite ≥3.25 / PostgreSQL)
    """
    if _table_exists(conn, "projects") or not _table_exists(conn, "teams"):
        return

    _exec(conn, "ALTER TABLE teams RENAME TO projects")
    if _column_exists(conn, "tasks", "team_id"):
        _exec(conn, "ALTER TABLE tasks RENAME COLUMN team_id TO project_id")
    if _table_exists(conn, "plans") and _column_exists(conn, "plans", "team_id"):
        _exec(conn, "ALTER TABLE plans RENAME COLUMN team_id TO project_id")

    for idx in ("idx_tasks_team_id", "idx_tasks_team_status",
                "idx_plans_team_id"):
        _exec(conn, f"DROP INDEX IF EXISTS {idx}")
    conn.commit()


def _drop_legacy_agents(conn) -> None:
    """레거시 agents 테이블 및 관련 FK 컬럼을 스키마 생성 전에 제거 (멱등).

    새 SQLITE_SCHEMA에 agents가 없으므로, 기존 tasks.assignee_id → agents(id) FK가
    남아있으면 foreign_keys=ON 상태에서 충돌한다. init_db의 executescript 전에 실행.
    """
    if not _table_exists(conn, "agents"):
        return

    # tasks의 assignee_id FK가 agents를 참조하므로, agents DROP 전에 tasks를 먼저 재생성
    if _column_exists(conn, "tasks", "assignee_id"):
        if _is_pg(conn):
            _exec(conn, "ALTER TABLE tasks DROP COLUMN assignee_id")
        else:
            # 현재 tasks에 plan_id/position이 있을 수도 없을 수도 있음
            has_plan_id = _column_exists(conn, "tasks", "plan_id")
            plan_cols = ", plan_id TEXT, position INTEGER" if has_plan_id else ""
            plan_select = ", plan_id, position" if has_plan_id else ""

            _exec(conn, f"""CREATE TABLE tasks_new (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL REFERENCES projects(id),
                title TEXT NOT NULL, description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Backlog'
                    CHECK(status IN ('Backlog','Todo','InProgress','Review','Done','Rejected')),
                priority TEXT NOT NULL DEFAULT 'Medium'
                    CHECK(priority IN ('Low','Medium','High','Critical')),
                is_blocked INTEGER NOT NULL DEFAULT 0, blocker_reason TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')){plan_cols}
            )""")
            _exec(conn, f"""INSERT INTO tasks_new
                SELECT id, project_id, title, description, status, priority,
                       is_blocked, blocker_reason, version, created_at, updated_at{plan_select}
                FROM tasks""")
            _exec(conn, "DROP TABLE tasks")
            _exec(conn, "ALTER TABLE tasks_new RENAME TO tasks")

    # agents 테이블 제거 (tasks FK 해소 후)
    _exec(conn, "DROP TABLE IF EXISTS agents")
    _exec(conn, "DROP INDEX IF EXISTS idx_agents_project_id")
    _exec(conn, "DROP INDEX IF EXISTS idx_tasks_assignee_id")

    # notes: agent_id 컬럼 제거
    if _column_exists(conn, "notes", "agent_id"):
        if _is_pg(conn):
            _exec(conn, "ALTER TABLE notes DROP COLUMN agent_id")
        else:
            _exec(conn, """CREATE TABLE notes_new (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                note_type TEXT NOT NULL DEFAULT 'progress'
                    CHECK(note_type IN ('progress','blocker','handoff','review','system')),
                created_at TEXT DEFAULT (datetime('now'))
            )""")
            _exec(conn, """INSERT INTO notes_new
                SELECT id, task_id, content, note_type, created_at
                FROM notes""")
            _exec(conn, "DROP TABLE notes")
            _exec(conn, "ALTER TABLE notes_new RENAME TO notes")

    conn.commit()


# ── Migrations (Phase 1) ──────────────────────────────────────────────────
#
# schema_migrations 기반 멱등 러너. CREATE TABLE IF NOT EXISTS만으로는
# ALTER TABLE(컬럼 추가)의 멱등성을 보장할 수 없으므로 버전 추적이 필요하다.

_SCHEMA_MIGRATIONS_SQLITE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT DEFAULT (datetime('now'))
)
"""

_SCHEMA_MIGRATIONS_PG = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMP DEFAULT NOW()
)
"""


def _column_exists(conn, table: str, column: str) -> bool:
    if _is_pg(conn):
        row = _exec(
            conn,
            "SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name=%s",
            (table, column),
        ).fetchone()
        return row is not None
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == column for r in cur.fetchall())


def _migration_applied(conn, version: int) -> bool:
    row = _exec(conn, "SELECT 1 FROM schema_migrations WHERE version=%s", (version,)).fetchone()
    return row is not None


def _record_migration(conn, version: int, name: str) -> None:
    _exec(
        conn,
        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (%s,%s,%s)",
        (version, name, _now()),
    )


def _mig_create_plans(conn) -> None:
    # 플랜은 프로젝트(레포당 1개)를 더 작은 의도 단위로 쪼갠다. project_id에 매단다.
    if _is_pg(conn):
        _exec(conn, """CREATE TABLE IF NOT EXISTS plans (
            id              TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL REFERENCES projects(id),
            title           TEXT NOT NULL,
            goal            TEXT DEFAULT '',
            scope_in        TEXT DEFAULT '',
            scope_out       TEXT DEFAULT '',
            archived_at     TIMESTAMP,
            cancelled_at    TIMESTAMP,
            on_hold_at      TIMESTAMP,
            started_at      TIMESTAMP,
            completed_at    TIMESTAMP,
            created_at      TIMESTAMP DEFAULT NOW()
        )""")
    else:
        _exec(conn, """CREATE TABLE IF NOT EXISTS plans (
            id              TEXT PRIMARY KEY,
            project_id         TEXT NOT NULL REFERENCES projects(id),
            title           TEXT NOT NULL,
            goal            TEXT DEFAULT '',
            scope_in        TEXT DEFAULT '',
            scope_out       TEXT DEFAULT '',
            archived_at     TEXT,
            cancelled_at    TEXT,
            on_hold_at      TEXT,
            started_at      TEXT,
            completed_at    TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        )""")
    _exec(conn, "CREATE INDEX IF NOT EXISTS idx_plans_project_id ON plans(project_id)")


def _mig_add_plan_id(conn) -> None:
    if not _column_exists(conn, "tasks", "plan_id"):
        _exec(conn, "ALTER TABLE tasks ADD COLUMN plan_id TEXT REFERENCES plans(id)")
    _exec(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_plan_id ON tasks(plan_id)")


def _mig_add_position(conn) -> None:
    if not _column_exists(conn, "tasks", "position"):
        _exec(conn, "ALTER TABLE tasks ADD COLUMN position INTEGER")
    _exec(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_plan_position ON tasks(plan_id, position)")


def _mig_drop_agents(conn) -> None:
    """agents 테이블 및 관련 컬럼(tasks.assignee_id, notes.agent_id) 제거.

    단일 세션 모델에서 agents 개념이 불필요하므로 삭제한다.
    SQLite는 DROP COLUMN을 3.35.0+ 에서 지원하지만, 안전하게 재생성한다.
    """
    _exec(conn, "DROP TABLE IF EXISTS agents")
    _exec(conn, "DROP INDEX IF EXISTS idx_agents_project_id")
    _exec(conn, "DROP INDEX IF EXISTS idx_tasks_assignee_id")

    # tasks: assignee_id 컬럼 제거 (SQLite 재생성)
    if _column_exists(conn, "tasks", "assignee_id"):
        if _is_pg(conn):
            _exec(conn, "ALTER TABLE tasks DROP COLUMN assignee_id")
        else:
            _exec(conn, """CREATE TABLE tasks_new (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id),
                title TEXT NOT NULL, description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Backlog'
                    CHECK(status IN ('Backlog','Todo','InProgress','Review','Done','Rejected')),
                priority TEXT NOT NULL DEFAULT 'Medium'
                    CHECK(priority IN ('Low','Medium','High','Critical')),
                is_blocked INTEGER NOT NULL DEFAULT 0, blocker_reason TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                plan_id TEXT REFERENCES plans(id), position INTEGER
            )""")
            _exec(conn, """INSERT INTO tasks_new
                SELECT id, project_id, title, description, status, priority,
                       is_blocked, blocker_reason, version, created_at, updated_at,
                       plan_id, position
                FROM tasks""")
            _exec(conn, "DROP TABLE tasks")
            _exec(conn, "ALTER TABLE tasks_new RENAME TO tasks")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_project_status ON tasks(project_id, status)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_plan_id ON tasks(plan_id)")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_tasks_plan_position ON tasks(plan_id, position)")

    # notes: agent_id 컬럼 제거
    if _column_exists(conn, "notes", "agent_id"):
        if _is_pg(conn):
            _exec(conn, "ALTER TABLE notes DROP COLUMN agent_id")
        else:
            _exec(conn, """CREATE TABLE notes_new (
                id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                note_type TEXT NOT NULL DEFAULT 'progress'
                    CHECK(note_type IN ('progress','blocker','handoff','review','system')),
                created_at TEXT DEFAULT (datetime('now'))
            )""")
            _exec(conn, """INSERT INTO notes_new
                SELECT id, task_id, content, note_type, created_at
                FROM notes""")
            _exec(conn, "DROP TABLE notes")
            _exec(conn, "ALTER TABLE notes_new RENAME TO notes")
            _exec(conn, "CREATE INDEX IF NOT EXISTS idx_notes_task_type_created ON notes(task_id, note_type, created_at DESC)")


_MIGRATIONS = [
    (1, "create_plans", _mig_create_plans),
    (2, "tasks_add_plan_id", _mig_add_plan_id),
    (3, "tasks_add_position", _mig_add_position),
    (4, "drop_agents", _mig_drop_agents),
]


def migrate_db(conn) -> None:
    """schema_migrations 기반 멱등 마이그레이션 러너 (Phase 1)."""
    if _is_pg(conn):
        _exec(conn, _SCHEMA_MIGRATIONS_PG)
    else:
        _exec(conn, _SCHEMA_MIGRATIONS_SQLITE)
    conn.commit()

    for version, name, fn in _MIGRATIONS:
        if not _migration_applied(conn, version):
            fn(conn)
            _record_migration(conn, version, name)
            conn.commit()


def _row_to_dict(row) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def _gen_id(prefix: str) -> str:
    return f"{prefix}-{nanoid(size=8)}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Notes ─────────────────────────────────────────────────────────────────

def _insert_note(conn, task_id: str, content: str, note_type: str = NoteType.SYSTEM) -> dict[str, Any]:
    note_id = _gen_id("note")
    now = _now()
    _exec(
        conn,
        "INSERT INTO notes (id, task_id, content, note_type, created_at) VALUES (%s,%s,%s,%s,%s)",
        (note_id, task_id, content, note_type, now),
    )
    return {"id": note_id, "task_id": task_id,
            "content": content, "note_type": note_type, "created_at": now}


# ── Projects ──────────────────────────────────────────────────────────────
# 프로젝트 = 레포 1개 = kanban.db 1개(싱글턴). "생성"이 아니라 레포당 1회 init한다.

def init_project(conn, name: str) -> dict[str, Any]:
    """이 레포의 프로젝트를 준비한다 (get-or-create, 멱등).

    같은 name의 프로젝트가 있으면 그대로 반환하고, 없으면 생성한다.
    """
    existing = _exec(conn, "SELECT * FROM projects WHERE name=%s", (name,)).fetchone()
    if existing is not None:
        p = _row_to_dict(existing)
        return {"id": p["id"], "name": p["name"], "created_at": p["created_at"],
                "message": f"프로젝트 '{name}'을 사용합니다 (기존)."}

    project_id = _gen_id("project")
    now = _now()
    _exec(conn, "INSERT INTO projects (id, name, created_at, config) VALUES (%s,%s,%s,%s)",
          (project_id, name, now, "{}"))
    conn.commit()
    return {"id": project_id, "name": name, "created_at": now,
            "message": f"프로젝트 '{name}'이 초기화되었습니다."}


def get_project(conn, project_id: str) -> dict[str, Any]:
    row = _exec(conn, "SELECT * FROM projects WHERE id=%s", (project_id,)).fetchone()
    if row is None:
        raise NotFoundError("프로젝트", project_id)
    return _row_to_dict(row)


# ── Tasks ─────────────────────────────────────────────────────────────────

def create_task(
    conn,
    project_id: str,
    title: str,
    description: str = "",
    priority: str = Priority.MEDIUM,
    plan_id: str | None = None,
    position: int | None = None,
) -> dict[str, Any]:
    get_project(conn, project_id)
    task_id = _gen_id("task")
    now = _now()

    is_blocked_val = False if _is_pg(conn) else 0
    _exec(
        conn,
        """INSERT INTO tasks (id, project_id, title, description, status, priority,
           is_blocked, blocker_reason, version, created_at, updated_at,
           plan_id, position)
           VALUES (%s,%s,%s,%s,%s,%s,%s,NULL,1,%s,%s,%s,%s)""",
        (task_id, project_id, title, description, "Backlog", priority,
         is_blocked_val, now, now, plan_id, position),
    )

    _insert_note(conn, task_id, f"Task created: {title}", "system")
    conn.commit()

    return {"id": task_id, "title": title, "status": "Backlog", "priority": priority,
            "version": 1, "created_at": now,
            "plan_id": plan_id, "position": position,
            "message": f"작업 '{title}'이 Backlog에 추가되었습니다."}


def get_task(conn, task_id: str) -> dict[str, Any]:
    row = _exec(conn, "SELECT * FROM tasks WHERE id=%s", (task_id,)).fetchone()
    if row is None:
        raise NotFoundError("작업", task_id)
    return _row_to_dict(row)


def update_task_status(
    conn,
    task_id: str,
    new_status: str,
    expected_version: int,
    comment: str | None = None,
) -> dict[str, Any]:
    task = get_task(conn, task_id)
    validate_transition(task["status"], new_status)

    project = get_project(conn, task["project_id"])
    config = json.loads(project["config"]) if project["config"] else {}
    wip_limits = config.get("wip_limits", {})
    if new_status in wip_limits:
        current_count = _exec(
            conn,
            "SELECT COUNT(*) as cnt FROM tasks WHERE project_id=%s AND status=%s",
            (task["project_id"], new_status),
        ).fetchone()["cnt"]
        if current_count >= wip_limits[new_status]:
            raise WipLimitExceededError(new_status, wip_limits[new_status])

    now = _now()
    cur = _exec(
        conn,
        "UPDATE tasks SET status=%s, version=version+1, updated_at=%s WHERE id=%s AND version=%s",
        (new_status, now, task_id, expected_version),
    )
    if cur.rowcount == 0:
        current = get_task(conn, task_id)
        raise VersionConflictError(current["version"], current["status"])

    _insert_note(conn, task_id,
                 f"Status changed: {task['status']} → {new_status}", "system")

    if comment:
        _insert_note(conn, task_id, comment, "progress")

    _update_plan_timestamps(conn, task.get("plan_id"), new_status)

    conn.commit()
    updated = get_task(conn, task_id)
    return {"task_id": task_id, "title": task["title"],
            "previous_status": task["status"], "new_status": new_status,
            "version": updated["version"], "updated_at": now,
            "project_id": task["project_id"],
            "message": f"상태가 '{task['status']}' → '{new_status}'로 변경되었습니다."}


# ── Plans (Phase 1) ───────────────────────────────────────────────────────
#
# 플랜은 프로젝트(레포당 1개)를 더 작은 의도 단위로 쪼갠다.

def create_plan(conn, project_id: str, title: str, goal: str = "",
                scope_in: str = "", scope_out: str = "") -> dict[str, Any]:
    get_project(conn, project_id)
    plan_id = _gen_id("plan")
    now = _now()
    _exec(
        conn,
        """INSERT INTO plans (id, project_id, title, goal, scope_in, scope_out, created_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (plan_id, project_id, title, goal, scope_in, scope_out, now),
    )
    conn.commit()
    return {"id": plan_id, "project_id": project_id, "title": title, "goal": goal,
            "scope_in": scope_in, "scope_out": scope_out, "created_at": now,
            "message": f"플랜 '{title}'이 생성되었습니다."}


def _derive_plan_state(counts: dict[str, int], blocked: int) -> str:
    """태스크 상태 집계에서 플랜 파생 상태를 계산 (compute-on-read).

    우선순위: blocked > active > completed > planned. 정확히 하나만 반환.
    """
    total = sum(counts.values())
    if blocked > 0:
        return "blocked"
    if counts.get("InProgress", 0) + counts.get("Review", 0) > 0:
        return "active"
    if total > 0 and counts.get("Done", 0) + counts.get("Rejected", 0) == total:
        return "completed"
    return "planned"


def _plan_task_stats(conn, plan_id: str) -> tuple[dict[str, int], int]:
    is_blk = True if _is_pg(conn) else 1
    rows = _exec(
        conn,
        """SELECT status, COUNT(*) AS cnt,
                  SUM(CASE WHEN is_blocked=%s THEN 1 ELSE 0 END) AS blk
           FROM tasks WHERE plan_id=%s GROUP BY status""",
        (is_blk, plan_id),
    ).fetchall()
    counts: dict[str, int] = {}
    blocked = 0
    for r in rows:
        r = dict(r)
        counts[r["status"]] = r["cnt"]
        blocked += r["blk"] or 0
    return counts, blocked


def _update_plan_timestamps(conn, plan_id: str | None, new_status: str) -> None:
    """태스크 상태 변경 시 플랜의 started_at/completed_at를 자동 갱신.

    상태(파생)는 저장하지 않지만 타임스탬프는 전이 시점을 알아야 하므로 여기서 기록한다.
    """
    if not plan_id:
        return

    now = _now()
    if new_status == "InProgress":
        _exec(conn, "UPDATE plans SET started_at=%s WHERE id=%s AND started_at IS NULL",
              (now, plan_id))

    stat = _exec(
        conn,
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN status IN ('Done','Rejected') THEN 1 ELSE 0 END) AS done
           FROM tasks WHERE plan_id=%s""",
        (plan_id,),
    ).fetchone()
    stat = dict(stat)
    total = stat["total"] or 0
    done = stat["done"] or 0
    if total > 0 and done == total:
        _exec(conn, "UPDATE plans SET completed_at=%s WHERE id=%s AND completed_at IS NULL",
              (now, plan_id))
    else:
        _exec(conn, "UPDATE plans SET completed_at=NULL WHERE id=%s AND completed_at IS NOT NULL",
              (plan_id,))


def get_plan(conn, plan_id: str) -> dict[str, Any]:
    row = _exec(conn, "SELECT * FROM plans WHERE id=%s", (plan_id,)).fetchone()
    if row is None:
        raise NotFoundError("플랜", plan_id)
    plan = _row_to_dict(row)

    counts, blocked = _plan_task_stats(conn, plan_id)
    total = sum(counts.values())
    done = counts.get("Done", 0) + counts.get("Rejected", 0)

    task_rows = _exec(
        conn,
        """SELECT id, title, status, priority, position, is_blocked
           FROM tasks WHERE plan_id=%s ORDER BY position ASC, created_at ASC""",
        (plan_id,),
    ).fetchall()
    tasks = []
    for t in task_rows:
        t = dict(t)
        tasks.append({"id": t["id"], "title": t["title"], "status": t["status"],
                      "priority": t["priority"], "position": t["position"],
                      "is_blocked": bool(t["is_blocked"])})

    return {"id": plan["id"], "project_id": plan["project_id"], "title": plan["title"],
            "goal": plan["goal"], "scope_in": plan["scope_in"], "scope_out": plan["scope_out"],
            "derived_state": _derive_plan_state(counts, blocked), "counts": counts,
            "task_total": total, "task_done": done,
            "archived_at": plan["archived_at"], "cancelled_at": plan["cancelled_at"],
            "on_hold_at": plan["on_hold_at"], "started_at": plan["started_at"],
            "completed_at": plan["completed_at"], "created_at": plan["created_at"],
            "tasks": tasks}


def list_plans(conn, project_id: str) -> dict[str, Any]:
    get_project(conn, project_id)
    plan_rows = _exec(
        conn, "SELECT * FROM plans WHERE project_id=%s ORDER BY created_at ASC", (project_id,)
    ).fetchall()

    is_blk = True if _is_pg(conn) else 1
    stat_rows = _exec(
        conn,
        """SELECT plan_id, status, COUNT(*) AS cnt,
                  SUM(CASE WHEN is_blocked=%s THEN 1 ELSE 0 END) AS blk
           FROM tasks
           WHERE plan_id IN (SELECT id FROM plans WHERE project_id=%s)
           GROUP BY plan_id, status""",
        (is_blk, project_id),
    ).fetchall()
    stats: dict[str, dict[str, Any]] = {}
    for r in stat_rows:
        r = dict(r)
        s = stats.setdefault(r["plan_id"], {"counts": {}, "blocked": 0})
        s["counts"][r["status"]] = r["cnt"]
        s["blocked"] += r["blk"] or 0

    plans = []
    for p in plan_rows:
        p = dict(p)
        st = stats.get(p["id"], {"counts": {}, "blocked": 0})
        counts = st["counts"]
        total = sum(counts.values())
        done = counts.get("Done", 0) + counts.get("Rejected", 0)
        plans.append({"id": p["id"], "title": p["title"], "goal": p["goal"],
                      "derived_state": _derive_plan_state(counts, st["blocked"]),
                      "counts": counts, "task_total": total, "task_done": done,
                      "started_at": p["started_at"], "completed_at": p["completed_at"],
                      "archived_at": p["archived_at"], "cancelled_at": p["cancelled_at"],
                      "on_hold_at": p["on_hold_at"]})
    return {"project_id": project_id, "plans": plans}


# ── Notes (public) ────────────────────────────────────────────────────────

def add_note(conn, task_id: str, content: str, note_type: str = NoteType.PROGRESS) -> dict[str, Any]:
    task = get_task(conn, task_id)

    note = _insert_note(conn, task_id, content, note_type)
    conn.commit()

    total = _exec(conn, "SELECT COUNT(*) as cnt FROM notes WHERE task_id=%s", (task_id,)).fetchone()["cnt"]
    return {
        "task_id": task_id,
        "project_id": task["project_id"],
        "note": {"id": note["id"], "content": content,
                 "note_type": note_type, "created_at": note["created_at"]},
        "total_notes": total,
        "message": f"메모가 추가되었습니다. (총 {total}개)",
    }


# ── Blocker ───────────────────────────────────────────────────────────────

def flag_blocker(conn, task_id: str, is_blocked: bool, expected_version: int, reason: str | None = None) -> dict[str, Any]:
    task = get_task(conn, task_id)

    if is_blocked and not reason:
        raise ValidationError("블로커 설정 시 reason은 필수입니다.")

    now = _now()
    blocker_reason = reason if is_blocked else None
    # SQLite: bool → 1/0, PostgreSQL: bool 네이티브
    is_blocked_val = is_blocked if _is_pg(conn) else (1 if is_blocked else 0)
    cur = _exec(
        conn,
        "UPDATE tasks SET is_blocked=%s, blocker_reason=%s, version=version+1, updated_at=%s WHERE id=%s AND version=%s",
        (is_blocked_val, blocker_reason, now, task_id, expected_version),
    )
    if cur.rowcount == 0:
        current = get_task(conn, task_id)
        raise VersionConflictError(current["version"], current["status"])

    if is_blocked:
        _insert_note(conn, task_id, f"Blocker set: {reason}", "system")
        _insert_note(conn, task_id, reason, "blocker")
    else:
        _insert_note(conn, task_id, "Blocker resolved", "system")

    conn.commit()
    updated = get_task(conn, task_id)
    msg = f"블로커가 설정되었습니다: '{reason}'" if is_blocked else "블로커가 해제되었습니다."
    return {"task_id": task_id, "title": task["title"], "is_blocked": is_blocked,
            "blocker_reason": blocker_reason, "version": updated["version"],
            "project_id": task["project_id"], "message": msg}


# ── Board Queries ─────────────────────────────────────────────────────────

def get_board(conn, project_id: str) -> dict[str, Any]:
    project = get_project(conn, project_id)
    board: dict[str, list] = {s: [] for s in ALL_STATUSES}
    counts: dict[str, int] = {s: 0 for s in ALL_STATUSES}

    sql = """
        SELECT t.id, t.title, t.status, t.priority, t.is_blocked, t.version,
               (SELECT n.content FROM notes n
                WHERE n.task_id = t.id AND n.note_type != 'system'
                ORDER BY n.created_at DESC LIMIT 1) AS latest_note
        FROM tasks t
        WHERE t.project_id = %s
        ORDER BY CASE t.priority
            WHEN 'Critical' THEN 0 WHEN 'High' THEN 1
            WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 END,
            t.created_at ASC
    """
    rows = _exec(conn, sql, (project_id,)).fetchall()

    for r in rows:
        r = dict(r)
        status = r["status"]
        counts[status] = counts.get(status, 0) + 1

        entry: dict[str, Any] = {
            "id": r["id"], "title": r["title"], "priority": r["priority"],
            "is_blocked": bool(r["is_blocked"]),
            "version": r["version"],
        }
        if r["latest_note"]:
            entry["latest_note"] = r["latest_note"]
        board[status].append(entry)

    config = json.loads(project["config"]) if project["config"] else {}
    wip_limits = config.get("wip_limits", {})
    wip_status = {s: f"{counts.get(s, 0)}/{limit}" for s, limit in wip_limits.items()}

    return {"project": project["name"], "counts": counts, "board": board,
            "wip_status": wip_status, "updated_at": _now()}


def get_task_detail(conn, task_id: str) -> dict[str, Any]:
    detail_sql = """
        SELECT t.*, p.id AS project_pk, p.name AS project_name
        FROM tasks t
        JOIN projects p ON t.project_id = p.id
        WHERE t.id = %s
    """
    row = _exec(conn, detail_sql, (task_id,)).fetchone()
    if row is None:
        raise NotFoundError("작업", task_id)
    task = dict(row)

    notes_sql = """
        SELECT n.id, n.content, n.note_type, n.created_at
        FROM notes n
        WHERE n.task_id = %s
        ORDER BY n.created_at ASC
    """
    notes = []
    for n in _exec(conn, notes_sql, (task_id,)).fetchall():
        n = dict(n)
        notes.append({"id": n["id"], "content": n["content"],
                      "note_type": n["note_type"], "created_at": n["created_at"]})

    return {"id": task["id"], "title": task["title"], "description": task["description"],
            "status": task["status"], "priority": task["priority"],
            "is_blocked": bool(task["is_blocked"]), "blocker_reason": task["blocker_reason"],
            "version": task["version"],
            "project": {"id": task["project_pk"], "name": task["project_name"]}, "notes": notes,
            "created_at": task["created_at"], "updated_at": task["updated_at"]}


def get_project_status(conn, project_id: str, activity_hours: int = 24) -> dict[str, Any]:
    project = get_project(conn, project_id)

    # 1) 상태별 카운트
    summary = {s: 0 for s in ALL_STATUSES}
    rows = _exec(conn, "SELECT status, COUNT(*) as cnt FROM tasks WHERE project_id=%s GROUP BY status", (project_id,)).fetchall()
    for r in rows:
        summary[r["status"]] = r["cnt"]

    # 2) 블로커
    blocker_sql = """
        SELECT t.id, t.title, t.blocker_reason
        FROM tasks t
        WHERE t.project_id = %s AND t.is_blocked = %s
    """
    is_blocked_val = True if _is_pg(conn) else 1
    blockers = []
    for b in _exec(conn, blocker_sql, (project_id, is_blocked_val)).fetchall():
        b = dict(b)
        blockers.append({"task_id": b["id"], "title": b["title"],
                         "reason": b["blocker_reason"]})

    # 3) 최근 활동
    if _is_pg(conn):
        time_sql = """SELECT n.content, n.created_at, t.title AS task_title
                      FROM notes n
                      JOIN tasks t ON n.task_id = t.id
                      WHERE t.project_id=%s AND n.note_type='system'
                      AND n.created_at >= NOW() - INTERVAL %s
                      ORDER BY n.created_at DESC LIMIT 20"""
        time_params = (project_id, f"{activity_hours} hours")
    else:
        time_sql = """SELECT n.content, n.created_at, t.title AS task_title
                      FROM notes n
                      JOIN tasks t ON n.task_id = t.id
                      WHERE t.project_id=%s AND n.note_type='system'
                      AND n.created_at >= datetime('now', %s)
                      ORDER BY n.created_at DESC LIMIT 20"""
        time_params = (project_id, f"-{activity_hours} hours")

    recent_activity = []
    for rn in _exec(conn, time_sql, time_params).fetchall():
        rn = dict(rn)
        recent_activity.append({
            "action": "status_change" if "Status changed" in rn["content"] else "update",
            "task": rn["task_title"], "detail": rn["content"], "at": rn["created_at"],
        })

    return {"project": project["name"], "summary": summary,
            "blockers": blockers, "recent_activity": recent_activity}


# ── Board Markdown (for Resources) ───────────────────────────────────────

def get_board_markdown(conn, project_id: str) -> str:
    data = get_board(conn, project_id)
    lines = [f"# {data['project']} - Kanban Board\n"]

    for status in ALL_STATUSES:
        tasks = data["board"][status]
        count = data["counts"][status]
        wip_info = f" [WIP: {data['wip_status'][status]}]" if status in data["wip_status"] else ""
        lines.append(f"## {status} ({count}){wip_info}")

        if not tasks:
            lines.append("_없음_\n")
            continue

        has_notes = any("latest_note" in t for t in tasks)
        if has_notes:
            lines.append("| ID | 작업 | 우선순위 | 최근 메모 | v |")
            lines.append("|----|------|---------|----------|---|")
            for t in tasks:
                blocked = " **[BLOCKED]**" if t["is_blocked"] else ""
                lines.append(f"| {t['id']} | {t['title']}{blocked} | {t['priority']} "
                             f"| {t.get('latest_note', '')} | {t['version']} |")
        else:
            lines.append("| ID | 작업 | 우선순위 | v |")
            lines.append("|----|------|---------|---|")
            for t in tasks:
                blocked = " **[BLOCKED]**" if t["is_blocked"] else ""
                lines.append(f"| {t['id']} | {t['title']}{blocked} | {t['priority']} "
                             f"| {t['version']} |")
        lines.append("")

    lines.append(f"최종 업데이트: {data['updated_at']}")
    return "\n".join(lines)


