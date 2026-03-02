"""FastAPI read-only REST API for Kanban Board Dashboard."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import (
    DB_PATH,
    get_board,
    get_connection,
    get_task_detail,
    get_team,
    get_team_status,
    init_db,
)
from .models import NotFoundError

app = FastAPI(
    title="Kanban Board Dashboard API",
    description="기존 MCP Kanban DB를 읽기 전용으로 조회하는 대시보드 API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@contextmanager
def get_readonly_conn() -> Generator[sqlite3.Connection, None, None]:
    """읽기 전용 DB 연결."""
    conn = get_connection(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


# ── Teams ────────────────────────────────────────────────────────────────


@app.get("/api/teams")
def list_teams() -> list[dict[str, Any]]:
    """모든 팀 목록 조회."""
    with get_readonly_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, created_at FROM teams ORDER BY created_at ASC"
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

    # /assets/* 정적 리소스 (JS, CSS, 이미지)
    assets_dir = DASHBOARD_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA fallback: /api 이외 모든 경로 → index.html
    @app.get("/{path:path}")
    def spa_fallback(path: str) -> FileResponse:
        file_path = DASHBOARD_DIR / path
        if file_path.is_file() and not path.startswith("api"):
            return FileResponse(str(file_path))
        return FileResponse(str(DASHBOARD_DIR / "index.html"))

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(str(DASHBOARD_DIR / "index.html"))


_mount_dashboard()


# ── Entrypoint ──────────────────────────────────────────────────────────

PORT = 48080


if __name__ == "__main__":
    import uvicorn

    conn = get_connection(DB_PATH)
    init_db(conn)
    conn.close()
    uvicorn.run(app, host="127.0.0.1", port=PORT)
