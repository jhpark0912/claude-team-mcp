"""FastAPI read-only REST API for Kanban Board Dashboard."""

from __future__ import annotations

import mimetypes
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

# Windows 레지스트리에서 .js MIME 타입이 text/plain으로 등록된 경우 보정
# 브라우저는 module script의 MIME이 text/plain이면 실행을 거부한다
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import (
    _exec,
    get_board,
    get_connection,
    get_pooled_connection,
    get_task_detail,
    get_team,
    get_team_status,
    init_db,
    return_pooled_connection,
)
from .models import NotFoundError

app = FastAPI(
    title="AI-Board API",
    description="AI-Board MCP DB를 읽기 전용으로 조회하는 대시보드 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@contextmanager
def get_readonly_conn() -> Generator[Any, None, None]:
    """읽기 전용 DB 연결 (PostgreSQL은 커넥션 풀 사용)."""
    conn = get_pooled_connection()
    try:
        yield conn
    finally:
        return_pooled_connection(conn)


# ── Teams ────────────────────────────────────────────────────────────────


@app.get("/api/teams")
def list_teams() -> list[dict[str, Any]]:
    """모든 팀 목록 조회."""
    with get_readonly_conn() as conn:
        rows = _exec(
            conn, "SELECT id, name, created_at FROM teams ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


# ── Board ────────────────────────────────────────────────────────────────


@app.get("/api/board/{team_id}")
def read_board(team_id: str) -> dict[str, Any]:
    """칸반보드 상태별 작업 목록 조회."""
    with get_readonly_conn() as conn:
        try:
            return get_board(conn, team_id)
        except NotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))


# ── Task Detail ──────────────────────────────────────────────────────────


@app.get("/api/tasks/{task_id}")
def read_task_detail(task_id: str) -> dict[str, Any]:
    """작업 상세 정보 조회 (노트 포함)."""
    with get_readonly_conn() as conn:
        try:
            return get_task_detail(conn, task_id)
        except NotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))


# ── Team Status ──────────────────────────────────────────────────────────


@app.get("/api/team-status/{team_id}")
def read_team_status(team_id: str, activity_hours: int = 24) -> dict[str, Any]:
    """팀 통계, 에이전트별 워크로드, 블로커 요약."""
    with get_readonly_conn() as conn:
        try:
            return get_team_status(conn, team_id, activity_hours)
        except NotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))


# ── Static Files (Dashboard) ───────────────────────────────────────────

DASHBOARD_DIR = Path(__file__).parent.parent.parent.parent / "agent-kanban-dashboard" / "dist"


def _mount_dashboard() -> None:
    """dist/ 폴더가 존재하면 정적 파일 서빙을 마운트한다."""
    if not DASHBOARD_DIR.is_dir():
        return

    # SPA fallback: /api 이외 모든 경로 → index.html
    # StaticFiles를 최하위에 마운트하여 정적 파일(JS/CSS)의 MIME 타입을 자동 감지
    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(DASHBOARD_DIR / "index.html"))

    app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


_mount_dashboard()


# ── Entrypoint ──────────────────────────────────────────────────────────

PORT = 48080


if __name__ == "__main__":
    import uvicorn

    conn = get_connection()
    init_db(conn)
    conn.close()
    uvicorn.run(app, host="127.0.0.1", port=PORT)
