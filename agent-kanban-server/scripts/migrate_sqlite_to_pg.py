"""SQLite → PostgreSQL 마이그레이션 스크립트.

사용법:
    python scripts/migrate_sqlite_to_pg.py [--dry-run] [--db-path <sqlite_path>]

환경변수:
    KANBAN_DB_HOST, KANBAN_DB_PORT, KANBAN_DB_USER, KANBAN_DB_PASSWORD, KANBAN_DB_NAME
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# .env 파일 자동 로드 (스크립트 위치 기준 상위 디렉토리)
load_dotenv(Path(__file__).parent.parent / ".env")

# ── 설정 ──────────────────────────────────────────────────────────────────

DEFAULT_SQLITE_PATH = Path(__file__).parent.parent / "kanban.db"

PG_CONFIG = {
    "host": os.environ.get("KANBAN_DB_HOST", "localhost"),
    "port": int(os.environ.get("KANBAN_DB_PORT", "5432")),
    "user": os.environ.get("KANBAN_DB_USER", "ai_board_user"),
    "password": os.environ.get("KANBAN_DB_PASSWORD", ""),
    "dbname": os.environ.get("KANBAN_DB_NAME", "ai_board"),
}

TABLES_ORDER = ["teams", "agents", "tasks", "notes"]

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT NOW(),
    config      TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    team_id     TEXT NOT NULL REFERENCES teams(id),
    name        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'Developer'
                CHECK(role IN ('PM','Developer','Reviewer','Tester','Designer')),
    created_at  TIMESTAMP DEFAULT NOW()
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
    is_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
    blocker_reason TEXT,
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    agent_id    TEXT NOT NULL,
    content     TEXT NOT NULL,
    note_type   TEXT NOT NULL DEFAULT 'progress'
                CHECK(note_type IN ('progress','blocker','handoff','review','system')),
    created_at  TIMESTAMP DEFAULT NOW()
);
"""

# ── SQLite 읽기 ────────────────────────────────────────────────────────────

def read_sqlite(db_path: Path) -> dict[str, list[dict]]:
    print(f"[SQLite] 연결: {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    data: dict[str, list[dict]] = {}
    for table in TABLES_ORDER:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        data[table] = [dict(row) for row in rows]
        print(f"  {table}: {len(data[table])}건")

    conn.close()
    return data


# ── 타입 변환 ──────────────────────────────────────────────────────────────

def _convert_row(table: str, row: dict) -> dict:
    """SQLite 타입을 PostgreSQL 타입으로 변환."""
    row = dict(row)
    if table == "tasks":
        # INTEGER(0/1) → Python bool → PostgreSQL BOOLEAN
        row["is_blocked"] = bool(row.get("is_blocked", 0))
    return row


# ── PostgreSQL 적재 ────────────────────────────────────────────────────────

def init_pg_schema(pg_conn) -> None:
    cur = pg_conn.cursor()
    for statement in PG_SCHEMA.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            cur.execute(stmt)
    pg_conn.commit()
    print("[PostgreSQL] 스키마 초기화 완료")


INSERT_SQL = {
    "teams": """
        INSERT INTO teams (id, name, created_at, config)
        VALUES (%(id)s, %(name)s, %(created_at)s, %(config)s)
        ON CONFLICT (id) DO NOTHING
    """,
    "agents": """
        INSERT INTO agents (id, team_id, name, role, created_at)
        VALUES (%(id)s, %(team_id)s, %(name)s, %(role)s, %(created_at)s)
        ON CONFLICT (id) DO NOTHING
    """,
    "tasks": """
        INSERT INTO tasks (id, team_id, title, description, status, priority,
                           assignee_id, is_blocked, blocker_reason, version,
                           created_at, updated_at)
        VALUES (%(id)s, %(team_id)s, %(title)s, %(description)s, %(status)s,
                %(priority)s, %(assignee_id)s, %(is_blocked)s, %(blocker_reason)s,
                %(version)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO NOTHING
    """,
    "notes": """
        INSERT INTO notes (id, task_id, agent_id, content, note_type, created_at)
        VALUES (%(id)s, %(task_id)s, %(agent_id)s, %(content)s, %(note_type)s, %(created_at)s)
        ON CONFLICT (id) DO NOTHING
    """,
}


def migrate_table(pg_conn, table: str, rows: list[dict], dry_run: bool) -> int:
    if not rows:
        print(f"  {table}: 0건 (건너뜀)")
        return 0

    converted = [_convert_row(table, row) for row in rows]

    if dry_run:
        print(f"  {table}: {len(converted)}건 (dry-run, 실제 적재 안 함)")
        return len(converted)

    cur = pg_conn.cursor()
    inserted = 0
    for row in converted:
        cur.execute(INSERT_SQL[table], row)
        inserted += cur.rowcount

    pg_conn.commit()
    print(f"  {table}: {len(converted)}건 시도 / {inserted}건 삽입")
    return inserted


# ── 검증 ──────────────────────────────────────────────────────────────────

def verify(sqlite_data: dict[str, list[dict]], pg_conn) -> bool:
    print("\n[검증] 레코드 수 비교")
    cur = pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    all_ok = True

    for table in TABLES_ORDER:
        sqlite_count = len(sqlite_data[table])
        cur.execute(f"SELECT COUNT(*) as cnt FROM {table}")
        pg_count = cur.fetchone()["cnt"]

        status = "OK" if sqlite_count == pg_count else "MISMATCH"
        print(f"  {table}: SQLite={sqlite_count} / PostgreSQL={pg_count} [{status}]")
        if status != "OK":
            all_ok = False

    return all_ok


# ── 메인 ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SQLite → PostgreSQL 마이그레이션")
    parser.add_argument(
        "--dry-run", action="store_true", help="실제 적재 없이 데이터만 읽고 출력"
    )
    parser.add_argument(
        "--db-path", type=str, default=str(DEFAULT_SQLITE_PATH), help="SQLite DB 경로"
    )
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"[오류] SQLite DB 파일을 찾을 수 없습니다: {db_path}", file=sys.stderr)
        sys.exit(1)

    # 1. SQLite 읽기
    print("=" * 50)
    print("1단계: SQLite 데이터 읽기")
    print("=" * 50)
    sqlite_data = read_sqlite(db_path)

    # 2. PostgreSQL 연결
    print("\n" + "=" * 50)
    print("2단계: PostgreSQL 연결")
    print("=" * 50)
    if args.dry_run:
        print("[dry-run 모드] PostgreSQL 실제 연결 없이 진행")
        pg_conn = None
    else:
        print(f"[PostgreSQL] 연결: {PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
        pg_conn = psycopg2.connect(**PG_CONFIG)
        print("[PostgreSQL] 연결 성공")
        init_pg_schema(pg_conn)

    # 3. 데이터 이전
    print("\n" + "=" * 50)
    print("3단계: 데이터 이전")
    print("=" * 50)
    for table in TABLES_ORDER:
        migrate_table(pg_conn, table, sqlite_data[table], dry_run=args.dry_run)

    # 4. 검증
    if not args.dry_run and pg_conn:
        print("\n" + "=" * 50)
        print("4단계: 검증")
        print("=" * 50)
        ok = verify(sqlite_data, pg_conn)
        pg_conn.close()

        print("\n" + "=" * 50)
        if ok:
            print("마이그레이션 완료: 모든 레코드 수 일치")
        else:
            print("[경고] 일부 테이블 레코드 수 불일치. 위 내용 확인 필요.")
            sys.exit(1)
    else:
        print("\n[dry-run 완료] 실제 데이터는 변경되지 않았습니다.")

    print("=" * 50)


if __name__ == "__main__":
    main()
