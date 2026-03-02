# Agent Kanban MCP Server

Claude Agent Teams 협업을 위한 칸반보드 MCP 서버.
에이전트들이 작업 진행 상황을 DB에 기록하고, 대시보드에서 시각적으로 확인할 수 있다.

## 아키텍처

```
Claude Agent Teams
    │
    ├─ [stdio] ──→ MCP Server (server.py) ──→ SQLite DB (kanban.db)
    │                10 Tools / 3 Resources / 5 Prompts
    │
    └─ [browser] ──→ Dashboard (web.py:48080)  ──→ SQLite DB (read-only)
                     REST API + 정적 파일 서빙
```

- **MCP 서버**: Claude Code가 stdio로 자동 실행. 에이전트가 도구를 호출하여 DB에 기록
- **대시보드**: 별도 프로세스로 실행. 같은 DB를 읽기 전용으로 조회하여 칸반보드 표시

---

## Quick Start

```bash
# 의존성 설치
cd agent-kanban-server
uv sync

# MCP 서버 → Claude Code가 자동 실행 (수동 실행 불필요)
# 대시보드 → 별도 터미널에서 실행
uv run python -m agent_kanban.web
# → http://localhost:48080 접속

# 테스트
uv run pytest tests/ -v
```

## Claude Code MCP 설정

`~/.claude/mcp.json`에 추가:

```json
{
  "mcpServers": {
    "agent-kanban": {
      "command": "uv",
      "args": ["run", "--directory", "D:\\00.claude\\01.mcp\\agent-kanban-server", "python", "-m", "agent_kanban.server"]
    }
  }
}
```

### 권한 설정 (settings.local.json)

자동 승인이 필요한 도구 목록:

```json
{
  "permissions": {
    "allow": [
      "mcp__agent-kanban__create_team",
      "mcp__agent-kanban__add_agent",
      "mcp__agent-kanban__create_task",
      "mcp__agent-kanban__update_task_status",
      "mcp__agent-kanban__assign_task",
      "mcp__agent-kanban__add_note",
      "mcp__agent-kanban__flag_blocker",
      "mcp__agent-kanban__get_board",
      "mcp__agent-kanban__get_task_detail",
      "mcp__agent-kanban__get_team_status"
    ]
  }
}
```

---

## 사용 가이드

### Phase 1: 팀 구성

```
1. create_team("프로젝트명")
   → { id: "team-xxxxxxxx", name: "프로젝트명" }

2. add_agent(team_id, "이름", "역할")
   역할: PM | Developer | Reviewer | Tester | Designer
   → { id: "agent-xxxxxxxx" }
```

**예시:**
```
create_team("Payment Refactoring")          → team-pay01
add_agent(team-pay01, "Alice", "PM")        → agent-alice
add_agent(team-pay01, "Bob", "Developer")   → agent-bob
add_agent(team-pay01, "Charlie", "Reviewer")→ agent-charlie
```

### Phase 2: 작업 생성

```
create_task(team_id, "제목", description?, priority?, assignee_id?)
  priority: Low | Medium | High | Critical (기본: Medium)
  → { id: "task-xxxxxxxx", status: "Backlog", version: 1 }
```

**예시:**
```
create_task(team-pay01, "결제 API 에러 핸들링 개선",
            priority="High", assignee_id=agent-bob)
```

> 생성 시 자동으로 시스템 노트가 추가됨:
> - "Task created by Bob (Developer): 결제 API 에러 핸들링 개선"
> - "Assigned to Bob (Developer)"

### Phase 3: 작업 진행

#### 상태 변경

```
update_task_status(task_id, "새상태", expected_version, agent_id?, comment?)
```

**상태 전이 규칙:**
```
Backlog → Todo → InProgress → Review → Done
  ↑                 ↑            │
  └── Todo ─────────└── Rejected ┘
```

**예시 (일반적인 작업 흐름):**
```
# 1. 작업 시작
update_task_status(task-001, "Todo", expected_version=1)
update_task_status(task-001, "InProgress", expected_version=2, comment="코딩 시작")

# 2. 진행 중 메모 추가
add_note(task-001, agent-bob, "PaymentService 리팩토링 50% 완료", note_type="progress")

# 3. 리뷰 요청
update_task_status(task-001, "Review", expected_version=3)
assign_task(task-001, agent-charlie, expected_version=4)
add_note(task-001, agent-bob, "리뷰 부탁드립니다. 변경 파일: ...", note_type="handoff")

# 4. 완료
update_task_status(task-001, "Done", expected_version=5, agent_id=agent-charlie)
```

#### 블로커 처리

```
# 블로커 설정 (reason 필수)
flag_blocker(task-001, is_blocked=true, expected_version=3, reason="외부 API 키 발급 대기")

# 블로커 해제
flag_blocker(task-001, is_blocked=false, expected_version=4)
```

#### 버전 충돌 해결 (Optimistic Locking)

여러 에이전트가 동시에 같은 태스크를 수정하면 `VERSION_CONFLICT` 발생:

```
# 충돌 발생 시:
get_task_detail(task-001)          → 현재 version 확인
update_task_status(task-001, "Done", expected_version=최신버전)
```

### Phase 4: 현황 조회

```
# 보드 전체 조회 (상태별 그룹)
get_board(team_id)
→ { counts: {Backlog: 3, Todo: 2, ...}, board: {...}, wip_status: {...} }

# 태스크 상세 (노트 포함)
get_task_detail(task_id)
→ { title, status, notes: [...], assigned_to: {...} }

# 팀 통계 (에이전트별 워크로드, 블로커)
get_team_status(team_id, activity_hours=24)
→ { summary: {...}, agents: [...], blockers: [...], recent_activity: [...] }
```

---

## 대시보드

### 운영 모드 (프로세스 1개)

```bash
uv run python -m agent_kanban.web
# → http://localhost:48080
```

`web.py`가 REST API + 빌드된 대시보드(dist/)를 함께 서빙.
DB 데이터가 변경되어도 재빌드 불필요 (JS가 런타임에 API 폴링).

### 개발 모드 (UI 수정 시)

```bash
# 터미널 1: API 서버
uv run python -m agent_kanban.web

# 터미널 2: Vite HMR
cd ../agent-kanban-dashboard
npm run dev
# → http://localhost:5173 (HMR 핫리로드)

# 수정 완료 후 빌드
npm run build
# → dist/ 갱신, 운영 모드로 복귀
```

### REST API 엔드포인트 (읽기 전용)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/teams` | 팀 목록 |
| GET | `/api/board/{team_id}` | 칸반보드 (상태별 그룹) |
| GET | `/api/tasks/{task_id}` | 태스크 상세 + 노트 |
| GET | `/api/team-status/{team_id}` | 팀 통계 + 워크로드 |

---

## MCP Resources

에이전트가 구독하여 보드 변경 알림을 받을 수 있는 리소스:

| URI | 설명 |
|-----|------|
| `kanban://rules` | 칸반 규칙 (상태 전이, 에러 처리, WIP 제한) |
| `kanban://board/{team_id}` | 보드 마크다운 스냅샷 (구독 가능) |
| `kanban://board/{team_id}/agents` | 에이전트 워크로드 테이블 (구독 가능) |

## MCP Prompts

에이전트에게 구조화된 작업 지침을 제공하는 프롬프트:

| Prompt | 파라미터 | 용도 |
|--------|---------|------|
| `kanban_system_prompt` | team_id, agent_id | 에이전트 초기화 (보드 현황 + 내 할당 작업) |
| `daily_standup_prompt` | team_id | 스탠드업 요약 생성 |
| `task_handoff_prompt` | task_id, from_agent_id, to_agent_id | 작업 인계 절차 |
| `blocker_escalation_prompt` | task_id | 블로커 분석 및 에스컬레이션 |
| `task_completion_prompt` | task_id, agent_id | 완료 체크리스트 |

---

## 핵심 개념

### Optimistic Locking (낙관적 잠금)

모든 태스크에 `version` 필드가 있으며, 수정 시 `expected_version`을 제출해야 한다.
다른 에이전트가 먼저 수정했으면 `VERSION_CONFLICT` 에러가 반환된다.

```
적용 대상: update_task_status, assign_task, flag_blocker
해결 방법: get_task_detail로 최신 version 확인 후 재시도
```

### WIP Limits (진행 중 작업 제한)

팀 config에 상태별 최대 작업 수를 설정할 수 있다:

```json
{ "wip_limits": { "InProgress": 3, "Review": 2 } }
```

제한 초과 시 `WIP_LIMIT_EXCEEDED` 에러 반환.

### Cross-Team Validation (팀 간 접근 제한)

에이전트는 자신이 속한 팀의 태스크만 조작할 수 있다.
다른 팀의 태스크에 접근하면 `CROSS_TEAM` 에러 반환.

### Auto System Notes (자동 시스템 노트)

아래 이벤트 발생 시 `note_type="system"` 노트가 자동 생성된다:
- 태스크 생성 / 상태 변경 / 할당 변경 / 블로커 설정·해제
