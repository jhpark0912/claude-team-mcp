# AI-Board MCP Server

Claude Agent Teams 협업을 위한 AI-Board MCP 서버.
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
      "args": ["run", "--directory", "/path/to/agent-kanban-server", "python", "-m", "agent_kanban.server"]
    }
  }
}
```

## 배포 모드

### 로컬 사용자 (stdio)

각자의 PC에서 독립적인 DB로 실행하는 기본 방식. **환경변수 설정 불필요.**

```bash
git clone <repo>
cd agent-kanban-server
uv sync
```

`~/.claude/mcp.json` 또는 Claude Desktop 설정:

```json
{
  "mcpServers": {
    "ai-board": {
      "command": "uv",
      "args": ["run", "python", "-m", "agent_kanban"],
      "cwd": "/path/to/agent-kanban-server"
    }
  }
}
```

### 클라우드 서버 접속 (SSE)

서버가 원격(GCP 등)에 배포된 경우, 여러 PC에서 동일한 DB를 공유할 수 있다.

```json
{
  "mcpServers": {
    "ai-board": {
      "url": "http://<서버IP>:8000/sse"
    }
  }
}
```

### 서버 직접 배포 (GCP e2-micro 기준)

환경변수 설정 후 실행. 참고: `.env.example`

```bash
# /etc/ai-board.env
MCP_TRANSPORT=sse
FASTMCP_HOST=0.0.0.0
FASTMCP_PORT=8000
KANBAN_DB_PATH=/var/lib/ai-board/kanban.db
```

systemd 서비스 등록 (`ai-board.service` 참조):

```bash
sudo cp ai-board.service /etc/systemd/system/
sudo systemctl enable --now ai-board
```

---

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

## CLAUDE.md 설정 (필수)

> **MCP 서버를 등록해도 Claude가 자발적으로 사용하지 않는다.**
> 프로젝트 루트의 `CLAUDE.md`에 아래 내용을 추가해야 에이전트가 칸반을 적극적으로 활용한다.

프로젝트 루트(`/path/to/your-project/CLAUDE.md`)에 다음을 추가:

```markdown
# 칸반 보드 (필수)

## 원칙
- **칸반 DB가 유일한 진실(Single Source of Truth)**이다.
- 작업 시작/완료 시 반드시 칸반 상태를 업데이트한다.
- /clear, /compact 후에도 get_board로 현재 상태를 복원한다.

## 워크플로우
1. 작업 시작 전: `get_board`로 현재 보드 확인
2. 작업 착수: `update_task_status` → InProgress + `add_note`로 계획 기록
3. 작업 완료: `update_task_status` → Done + `add_note`로 결과 기록
4. 블로커 발생: `flag_blocker`로 즉시 기록

## 팀 정보
- Team ID: `team-xxxxxxxx`
- 내 Agent ID: `agent-xxxxxxxx`
```

### 핵심 포인트

| 항목 | 설명 |
|------|------|
| DB = 유일한 진실 | 에이전트가 기억에 의존하지 않고 DB를 조회하도록 강제 |
| 워크플로우 명시 | 언제 어떤 도구를 호출할지 구체적으로 지시 |
| Team/Agent ID 기록 | 세션 복원 시 재설정 없이 바로 작업 가능 |

---

## Slash Commands (권장)

`.claude/commands/` 디렉토리에 단축 명령을 추가하면 MCP 호출을 보장할 수 있다.

### 설정 방법

```bash
mkdir -p .claude/commands
```

### /board — 보드 현황 조회

`.claude/commands/board.md`:
```markdown
get_board로 현재 칸반보드 상태를 조회하고 요약해줘.
팀 ID: team-xxxxxxxx

상태별 작업 수, 블로커 여부, 내 할당 작업을 정리해줘.
```

### /resume — 세션 복원

`.claude/commands/resume.md`:
```markdown
칸반보드에서 내 현재 상태를 복원해줘.

1. get_board(team-xxxxxxxx)로 보드 전체 조회
2. get_team_status(team-xxxxxxxx)로 팀 현황 확인
3. 내 에이전트(agent-xxxxxxxx)에 할당된 InProgress 작업 파악
4. 해당 작업의 get_task_detail로 최근 노트 확인
5. 이전 작업 컨텍스트를 요약해줘
```

### /done — 작업 완료 처리

`.claude/commands/done.md`:
```markdown
현재 진행 중인 작업을 완료 처리해줘.

1. get_board(team-xxxxxxxx)에서 내(agent-xxxxxxxx) InProgress 작업 확인
2. 해당 작업에 add_note로 완료 내용 기록
3. update_task_status로 Review 또는 Done으로 변경
4. 다음 할당 작업이 있으면 알려줘
```

### /plan — 작업 분해 및 생성

`.claude/commands/plan.md`:
```markdown
$ARGUMENTS 작업을 분석하고 칸반 태스크로 분해해줘.

1. 요구사항 분석
2. 하위 작업으로 분해 (각각 create_task)
3. 우선순위 설정 (Critical > High > Medium > Low)
4. 담당자 할당 (assign_task)
5. 보드 현황 요약
```

---

## 사용 시나리오

### 단일 세션 (일상 작업)

혼자 작업할 때의 전형적인 흐름:

```
# 1. 보드 확인
/board                          → 현재 상태 파악

# 2. 작업 선택 및 시작
update_task_status(task-001, "InProgress", version=2)
add_note(task-001, agent-me, "API 엔드포인트 구현 시작")

# 3. 작업 수행 (일반 코딩)
... 코드 작성 ...

# 4. 진행 기록
add_note(task-001, agent-me, "POST /api/users 구현 완료, 테스트 작성 중")

# 5. 완료
/done                           → 자동으로 상태 변경 + 노트 기록
```

### Agent Teams (병렬 작업)

Claude Code의 Agent Teams 기능으로 여러 에이전트가 병렬 작업할 때:

```
# Team Lead가 팀 구성
create_team("Feature-Auth")
add_agent(team-auth, "lead", "PM")
add_agent(team-auth, "backend", "Developer")
add_agent(team-auth, "frontend", "Developer")
add_agent(team-auth, "reviewer", "Reviewer")

# 작업 생성 및 할당
create_task(team-auth, "JWT 인증 구현", priority="High", assignee_id=agent-backend)
create_task(team-auth, "로그인 UI 구현", priority="High", assignee_id=agent-frontend)

# 각 에이전트는 자기 작업만 진행
# backend: update_task_status → InProgress → Review
# frontend: update_task_status → InProgress → Review
# reviewer: get_board로 Review 상태 작업 확인 → 리뷰 후 Done

# Optimistic Locking이 동시 수정 충돌을 방지
```

### 세션 복원 (/clear, /compact 후)

Claude Code에서 `/clear`나 `/compact`를 하면 대화 컨텍스트가 사라진다.
하지만 **칸반 DB에 모든 상태가 보존**되어 있으므로 복원 가능:

```
# 방법 1: Slash Command 사용
/resume                         → 자동으로 보드 조회 + 컨텍스트 복원

# 방법 2: 수동 복원
get_board(team-xxxxxxxx)        → 전체 현황
get_team_status(team-xxxxxxxx)  → 블로커, 활동 이력
get_task_detail(task-xxxxxxxx)  → 진행 중이던 작업의 노트 확인
```

> **CLAUDE.md에 Team ID / Agent ID를 기록해두면** `/clear` 후에도 ID를 다시 찾을 필요가 없다.

---

## 도구 레퍼런스

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

## 에러 코드

에이전트가 에러를 받았을 때 참고하는 표:

| 코드 | 원인 | 해결 |
|------|------|------|
| `VERSION_CONFLICT` | 다른 에이전트가 이미 수정함 (Optimistic Locking) | `get_task_detail`로 최신 version 확인 후 재시도 |
| `INVALID_TRANSITION` | 허용되지 않는 상태 전이 (예: Backlog → Done) | 상태 전이 규칙 확인. 응답에 `allowed_transitions` 포함 |
| `WIP_LIMIT_EXCEEDED` | 해당 상태의 진행 중 작업 수가 제한 초과 | 다른 작업을 먼저 완료 (Done/Rejected)하고 재시도 |
| `CROSS_TEAM_ERROR` | 에이전트가 다른 팀의 태스크에 접근 | 올바른 team_id / agent_id 확인 |
| `NOT_FOUND` | 팀/에이전트/태스크를 찾을 수 없음 | ID 오타 확인. `get_board`로 유효 ID 조회 |
| `VALIDATION_ERROR` | 필수 파라미터 누락 (예: 블로커 설정 시 reason 미제공) | 에러 메시지에 명시된 필수 값 제공 |

**에러 응답 형식:**
```json
{
  "error": "VERSION_CONFLICT",
  "message": "다른 에이전트가 이미 수정했습니다. get_task_detail로 최신 상태 조회 후 재시도하세요.",
  "current_version": 5,
  "current_status": "Review"
}
```

---

## 데이터 모델

4개 테이블로 구성. 상세 스키마는 [`docs/design/data-model.md`](docs/design/data-model.md) 참조.

```
Team (1) ──▶ (N) Agent
Team (1) ──▶ (N) Task ──▶ (N) Note
Task ──▶ Agent (assignee)
```

| 테이블 | 주요 필드 | 설명 |
|--------|----------|------|
| **teams** | id, name, config | 팀. config에 WIP 제한 설정 |
| **agents** | id, team_id, name, role | 팀 소속 에이전트 (PM/Developer/Reviewer/Tester/Designer) |
| **tasks** | id, team_id, status, priority, assignee_id, version | 작업 카드. version으로 Optimistic Locking |
| **notes** | id, task_id, agent_id, content, note_type | 작업 메모 (progress/blocker/handoff/review/system) |

**상태 머신:**
```
Backlog → Todo → InProgress → Review → Done
                    ↑            │
                    └── Rejected ┘
Todo → Backlog (우선순위 재조정)
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
다른 팀의 태스크에 접근하면 `CROSS_TEAM_ERROR` 에러 반환.

### Auto System Notes (자동 시스템 노트)

아래 이벤트 발생 시 `note_type="system"` 노트가 자동 생성된다:
- 태스크 생성 / 상태 변경 / 할당 변경 / 블로커 설정·해제

---

## 설계 문서

- [`docs/design/data-model.md`](docs/design/data-model.md) — ER 다이어그램, DB 스키마, 상태 머신
