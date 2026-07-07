"""MCP Kanban Board Server — workflow engine for a single Claude session."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.prompts import base
from pydantic import AnyUrl

from . import db
from .models import KanbanError

# ── Server Setup ──────────────────────────────────────────────────────────

mcp = FastMCP(
    "AI-Board",
    json_response=True,
)

_conn = None


def _is_conn_alive(conn) -> bool:
    """커넥션이 살아있는지 확인."""
    try:
        if db._is_pg(conn):
            return conn.closed == 0
        else:
            conn.execute("SELECT 1")
            return True
    except Exception:
        return False


def _get_conn():
    global _conn
    if _conn is None or not _is_conn_alive(_conn):
        _conn = db.get_connection()
        db.init_db(_conn)
        db.migrate_db(_conn)
    return _conn


# ── Helper ────────────────────────────────────────────────────────────────

async def _notify_board(ctx: Context, project_id: str) -> None:
    """Send resource updated notification for the board."""
    try:
        await ctx.session.send_resource_updated(AnyUrl(f"kanban://board/{project_id}"))
    except Exception:
        pass  # notification is best-effort


def _handle_error(e: KanbanError) -> dict[str, Any]:
    """Convert KanbanError to response dict."""
    return e.to_dict()


# ══════════════════════════════════════════════════════════════════════════
#  TOOLS (13)
# ══════════════════════════════════════════════════════════════════════════

# ── Configuration (2) ─────────────────────────────────────────────────────

@mcp.tool()
async def init_project(name: str, ctx: Context) -> dict[str, Any]:
    """이 레포의 프로젝트를 준비합니다 (레포당 1회, get-or-create). 같은 이름이 있으면 재사용."""
    conn = _get_conn()
    return db.init_project(conn, name)


@mcp.tool()
async def add_agent(project_id: str, name: str, role: str, ctx: Context) -> dict[str, Any]:
    """프로젝트에 에이전트를 추가합니다. role: PM, Developer, Reviewer, Tester, Designer"""
    conn = _get_conn()
    try:
        result = db.add_agent(conn, project_id, name, role)
        await _notify_board(ctx, project_id)
        return result
    except KanbanError as e:
        return _handle_error(e)


# ── Plans (3) ─────────────────────────────────────────────────────────────
# 플랜은 프로젝트(레포당 1개)를 더 작은 의도 단위로 쪼갠다.

@mcp.tool()
async def create_plan(
    project_id: str,
    title: str,
    ctx: Context,
    goal: str = "",
    scope_in: str = "",
    scope_out: str = "",
) -> dict[str, Any]:
    """프로젝트(project_id) 하위에 플랜(의도 + 경계)을 생성합니다. goal/scope_in/scope_out은 인터뷰 결과."""
    conn = _get_conn()
    try:
        return db.create_plan(conn, project_id, title, goal, scope_in, scope_out)
    except KanbanError as e:
        return _handle_error(e)


@mcp.tool()
async def get_plan(plan_id: str, ctx: Context) -> dict[str, Any]:
    """플랜 상세를 반환합니다. 파생 상태(planned/active/completed/blocked)와 태스크 목록 포함."""
    conn = _get_conn()
    try:
        return db.get_plan(conn, plan_id)
    except KanbanError as e:
        return _handle_error(e)


@mcp.tool()
async def list_plans(project_id: str, ctx: Context) -> dict[str, Any]:
    """프로젝트(project_id)별 플랜 목록 + 각 플랜의 파생 상태를 반환합니다."""
    conn = _get_conn()
    try:
        return db.list_plans(conn, project_id)
    except KanbanError as e:
        return _handle_error(e)


# ── Task Lifecycle (3) ────────────────────────────────────────────────────

@mcp.tool()
async def create_task(
    project_id: str,
    title: str,
    ctx: Context,
    description: str = "",
    priority: str = "Medium",
    assignee_id: str | None = None,
    plan_id: str | None = None,
    position: int | None = None,
) -> dict[str, Any]:
    """새 칸반 카드를 생성합니다. 초기 상태는 Backlog. priority: Low, Medium, High, Critical. description: 첫 줄은 작업 요약, 이후 레이블(관련/API/설정/참고)로 구분. plan_id/position: 플랜에 소속시키고 플랜 내 순서 지정(생략 시 미분류)"""
    conn = _get_conn()
    try:
        result = db.create_task(
            conn, project_id, title, description, priority, assignee_id,
            creator_agent_id=assignee_id, plan_id=plan_id, position=position,
        )
        await _notify_board(ctx, project_id)
        return result
    except KanbanError as e:
        return _handle_error(e)


@mcp.tool()
async def update_task_status(
    task_id: str,
    status: str,
    expected_version: int,
    ctx: Context,
    agent_id: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    """카드 상태를 변경합니다. 서버가 전이 규칙을 검증합니다. status: Backlog, Todo, InProgress, Review, Done, Rejected"""
    conn = _get_conn()
    try:
        result = db.update_task_status(
            conn, task_id, status, expected_version, agent_id, comment,
        )
        task = db.get_task(conn, task_id)
        await _notify_board(ctx, task["project_id"])
        return result
    except KanbanError as e:
        return _handle_error(e)


@mcp.tool()
async def assign_task(
    task_id: str,
    assignee_id: str,
    expected_version: int,
    ctx: Context,
) -> dict[str, Any]:
    """작업을 에이전트에게 할당합니다. 에이전트가 해당 task의 프로젝트 소속인지 서버에서 검증합니다."""
    conn = _get_conn()
    try:
        result = db.assign_task(conn, task_id, assignee_id, expected_version)
        task = db.get_task(conn, task_id)
        await _notify_board(ctx, task["project_id"])
        return result
    except KanbanError as e:
        return _handle_error(e)


# ── Collaboration (2) ─────────────────────────────────────────────────────

@mcp.tool()
async def add_note(
    task_id: str,
    agent_id: str,
    content: str,
    ctx: Context,
    note_type: str = "progress",
) -> dict[str, Any]:
    """카드에 진행사항 메모를 추가합니다. note_type: progress, blocker, handoff, review"""
    conn = _get_conn()
    try:
        result = db.add_note(conn, task_id, agent_id, content, note_type)
        task = db.get_task(conn, task_id)
        await _notify_board(ctx, task["project_id"])
        return result
    except KanbanError as e:
        return _handle_error(e)


@mcp.tool()
async def flag_blocker(
    task_id: str,
    is_blocked: bool,
    expected_version: int,
    ctx: Context,
    reason: str | None = None,
) -> dict[str, Any]:
    """작업에 블로커를 설정하거나 해제합니다. is_blocked=true 시 reason 필수."""
    conn = _get_conn()
    try:
        result = db.flag_blocker(conn, task_id, is_blocked, expected_version, reason)
        task = db.get_task(conn, task_id)
        await _notify_board(ctx, task["project_id"])
        return result
    except KanbanError as e:
        return _handle_error(e)


# ── Board Query (3) ───────────────────────────────────────────────────────

@mcp.tool()
async def get_board(project_id: str) -> dict[str, Any]:
    """칸반보드의 상태별 작업 목록을 조회합니다."""
    conn = _get_conn()
    try:
        return db.get_board(conn, project_id)
    except KanbanError as e:
        return _handle_error(e)


@mcp.tool()
async def get_task_detail(task_id: str) -> dict[str, Any]:
    """카드 상세 정보를 전체 노트 포함하여 조회합니다."""
    conn = _get_conn()
    try:
        return db.get_task_detail(conn, task_id)
    except KanbanError as e:
        return _handle_error(e)


@mcp.tool()
async def get_project_status(
    project_id: str,
    activity_hours: int = 24,
) -> dict[str, Any]:
    """프로젝트 전체 통계, 에이전트별 워크로드, 블로커를 요약합니다."""
    conn = _get_conn()
    try:
        return db.get_project_status(conn, project_id, activity_hours)
    except KanbanError as e:
        return _handle_error(e)


# ══════════════════════════════════════════════════════════════════════════
#  RESOURCES (3)
# ══════════════════════════════════════════════════════════════════════════

KANBAN_RULES = """# 칸반보드 기록 규칙

## 필수 기록 시점
1. 작업 시작: create_task → update_task_status(InProgress)
2. 진행 중: 아래 상황 발견 시 add_note(note_type="progress")로 기록
   - 예상과 다른 구조, 원본 버그, 설계 변경이 필요한 부분
   - 다른 모듈에 영향을 줄 수 있는 변경
   - 원본과 다르게 구현한 경우 (사유 포함)
3. Review 전환: add_note로 특이사항 기록 (없으면 "특이사항 없음")
4. 인계: assign_task + add_note(note_type="handoff")
5. 블로커: flag_blocker(is_blocked=true, reason="...")

## 상태 전이
Backlog → Todo → InProgress → Review → Done
                    ↑            │
                    └── Rejected ┘
- Todo → Backlog: 우선순위 재조정으로 대기열 복귀
- Backlog → InProgress: 불허. Todo를 거쳐야 함

## 동시성
expected_version 필수. 충돌 시 아래 에러 대응 참조.

## 에러 대응
- VERSION_CONFLICT → get_task_detail로 최신 조회 → expected_version 갱신 → 재시도
- INVALID_TRANSITION → 허용된 전이 목록 확인 → 올바른 상태로 재요청
- WIP_LIMIT_EXCEEDED → 다른 InProgress 작업을 Review/Done으로 먼저 이동
- CROSS_PROJECT_ERROR → 올바른 프로젝트의 에이전트 ID 확인
- VALIDATION_ERROR → 필수 파라미터 누락 확인 (예: 블로커 설정 시 reason 필수)

## Task Description 작성 규칙
첫 줄: 구체적인 작업 내용 (한 줄로 작업을 이해할 수 있어야 한다)

이후 필요한 정보를 레이블로 구분하여 작성:
  관련: 영향받는 파일, 모듈, 서비스
  API: 엔드포인트, HTTP 메서드 (해당 시)
  설정: 설정 파일, 환경변수 (해당 시)
  참고: 의존성, 선행 작업, 주의사항 (해당 시)

규칙:
- 첫 줄만으로 작업을 이해할 수 있어야 한다
- 한 줄에 여러 정보를 마침표로 이어붙이지 마라
- 해당 없는 레이블은 생략하라
- 마크다운 헤더(##) 사용 금지 (description 내부)
"""


@mcp.resource("kanban://rules")
def kanban_rules() -> str:
    """칸반 기록 규칙 (정적)"""
    return KANBAN_RULES


@mcp.resource("kanban://board/{project_id}")
def board_resource(project_id: str) -> str:
    """칸반보드 스냅샷 (구독 가능). task의 v 값을 expected_version으로 사용 가능."""
    conn = _get_conn()
    try:
        return db.get_board_markdown(conn, project_id)
    except KanbanError as e:
        return json.dumps(e.to_dict(), ensure_ascii=False)


@mcp.resource("kanban://board/{project_id}/agents")
def agents_resource(project_id: str) -> str:
    """에이전트 목록 + 작업량"""
    conn = _get_conn()
    try:
        return db.get_agents_markdown(conn, project_id)
    except KanbanError as e:
        return json.dumps(e.to_dict(), ensure_ascii=False)


# ══════════════════════════════════════════════════════════════════════════
#  PROMPTS (5)
# ══════════════════════════════════════════════════════════════════════════

@mcp.prompt(title="Kanban System Prompt")
def kanban_system_prompt(project_id: str, agent_id: str) -> str:
    """초기화 시 1회 사용. 보드 스냅샷과 에이전트 담당 작업을 포함합니다."""
    conn = _get_conn()
    try:
        project = db.get_project(conn, project_id)
        agent = db.get_agent(conn, agent_id)
        board_data = db.get_board(conn, project_id)

        # Agent's tasks
        my_tasks = db._exec(
            conn,
            "SELECT id, title, status, version FROM tasks WHERE assignee_id=%s AND status NOT IN ('Done','Rejected')",
            (agent_id,),
        ).fetchall()
        my_tasks_str = "\n".join(
            f'  "{t["title"]}" ({t["status"]} v{t["version"]})' for t in my_tasks
        ) or "  없음"

        counts = board_data["counts"]
        blockers_count = db._exec(
            conn,
            "SELECT COUNT(*) as cnt FROM tasks WHERE project_id=%s AND is_blocked=TRUE",
            (project_id,),
        ).fetchone()["cnt"]

        return f"""[칸반 에이전트] 프로젝트: {project['name']} / 역할: {agent['name']} ({agent['role']})

현재 보드 (초기화 시점 기준):
  InProgress {counts.get('InProgress', 0)}건 / Review {counts.get('Review', 0)}건 / 블로커 {blockers_count}건
  내 담당:
{my_tasks_str}
  ⚠ 이 정보는 초기화 시점 기준입니다. 작업 전 get_board로 최신 상태를 확인하세요.

작업 수행 시 반드시 칸반보드를 업데이트하세요:
- 시작: create_task 또는 update_task_status → InProgress
- 진행: add_note로 현황 기록
- 블로커: flag_blocker로 표시
- 완료: update_task_status → Done + add_note

규칙 상세: kanban://rules"""
    except KanbanError as e:
        return f"Error: {e.message}"


@mcp.prompt(title="Daily Standup")
def daily_standup_prompt(project_id: str) -> str:
    """일일 스탠드업 요약 생성을 위한 프롬프트."""
    conn = _get_conn()
    try:
        project = db.get_project(conn, project_id)
        return f"""{project['name']} 일일 스탠드업 요약을 생성하세요.
get_board와 get_project_status를 호출한 후 아래 형식으로 작성:

## 현황
Todo {{n}} / InProgress {{n}} / Review {{n}} / Done {{n}}

## 에이전트별
- {{agent}}: {{task_title}} ({{status}})

## 블로커
- {{task_title}} - {{reason}} (담당: {{agent}})

## 긴급
- {{priority가 High/Critical인 작업 목록}}

## 권장 액션
- {{다음에 해야 할 일 1~2개}}"""
    except KanbanError as e:
        return f"Error: {e.message}"


@mcp.prompt(title="Task Handoff")
def task_handoff_prompt(task_id: str, from_agent_id: str, to_agent_id: str) -> str:
    """작업 인계 시 사용. 필수 포함 항목을 명시합니다."""
    conn = _get_conn()
    try:
        task = db.get_task(conn, task_id)
        from_agent = db.get_agent(conn, from_agent_id)
        to_agent = db.get_agent(conn, to_agent_id)

        return f"""작업 인계: '{task['title']}'
From: {from_agent['name']} ({from_agent['role']}) → To: {to_agent['name']} ({to_agent['role']})

수행:
1. assign_task로 담당자 변경
2. add_note(note_type="handoff")로 인수인계 기록
   필수 포함:
   - 완료한 것: 어떤 작업을 끝냈는지
   - 남은 것: 아직 처리하지 않은 항목
   - 주의사항: 알려진 이슈, 엣지 케이스
   - 관련 파일 경로: 수정한 파일 목록
3. update_task_status로 상태 변경 (필요 시)"""
    except KanbanError as e:
        return f"Error: {e.message}"


@mcp.prompt(title="Blocker Escalation")
def blocker_escalation_prompt(task_id: str) -> str:
    """블로커 에스컬레이션 시 사용."""
    conn = _get_conn()
    try:
        task = db.get_task(conn, task_id)
        reason = task.get("blocker_reason", "알 수 없음")

        return f"""블로커 에스컬레이션: '{task['title']}'
사유: {reason}

수행:
1. get_task_detail(task_id)로 현재 상태 확인
2. get_board(project_id)로 영향받는 InProgress 작업 파악
3. 대안 검토 (mock, 우회, 다른 작업 먼저 진행)
4. add_note(note_type="blocker")로 분석 결과 기록
   필수 포함: 블로커 사유 / 영향 작업 목록 / 제안 대안 / 예상 해소 시점
5. PM에게 보고할 1-2줄 요약 생성"""
    except KanbanError as e:
        return f"Error: {e.message}"


@mcp.prompt(title="Task Completion")
def task_completion_prompt(task_id: str, agent_id: str) -> str:
    """작업 완료 처리 시 사용. 다음 우선순위 작업도 안내합니다."""
    conn = _get_conn()
    try:
        task = db.get_task(conn, task_id)
        agent = db.get_agent(conn, agent_id)

        # Find next priority task for this agent
        next_task = db._exec(
            conn,
            """SELECT title, priority FROM tasks
               WHERE assignee_id=%s AND status='Todo'
               ORDER BY
                 CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1
                              WHEN 'Medium' THEN 2 WHEN 'Low' THEN 3 END
               LIMIT 1""",
            (agent_id,),
        ).fetchone()

        next_info = "없음"
        if next_task:
            next_info = f'"{next_task["title"]}" ({next_task["priority"]})'

        return f"""작업 완료: '{task['title']}'

수행:
1. update_task_status → Done (expected_version 확인)
2. add_note로 최종 결과 기록
   필수 포함:
   - 변경 사항 요약: 무엇을 어떻게 바꿨는지
   - 테스트 결과: 검증 완료 여부
   - 후속 작업 여부: 추가 작업이 필요한지 (필요하면 create_task)
3. 다음 우선순위 작업 확인
   내 담당 Todo 중 priority 높은 것: {next_info}
   ⚠ 이 정보는 생성 시점 기준입니다. get_board로 최신 확인 권장."""
    except KanbanError as e:
        return f"Error: {e.message}"


# ── Entry Point ───────────────────────────────────────────────────────────

def main():
    import os
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
