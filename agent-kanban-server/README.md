# AI-Board MCP Server

칸반 보드를 워크플로우 엔진으로 쓰는 AI-Board MCP 서버.
`/plan`(기획) → `/team-run`(구현·자체QA·리뷰·Done 자율 순환) → `/retro`(회고·교훈 승격) →
`/resume`(세션 복원) 4개 커맨드가 이 서버 위에서 동작하며, 진행 상황과 판단 근거는
전부 DB(태스크/노트)에 남아 대시보드(session_board)에서 확인할 수 있다.

이 워크플로우는 **한 세션이 태스크를 순차로 진행**하는 것을 전제로 설계되었다
(여러 에이전트가 동시에 각자 태스크를 잡는 병렬 실행 단위가 아니다). 유일한 예외는
리뷰 단계에서 신선한 컨텍스트로 판정하는 Reviewer 서브에이전트다.

## 아키텍처

```
[로컬 모드]
Claude Code (단일 세션)
    │
    └─ [stdio] ──→ MCP Server (server.py) ──→ SQLite DB (kanban.db, 로컬)
                     10 Tools / 3 Resources / 5 Prompts

[클라우드 공유 모드 — 동일 사용자의 여러 PC 동기화용, 동시 병렬 작업 목적 아님]
Claude Code (PC-1) ──┐
Claude Code (PC-2) ──┼─ [stdio] ──→ MCP Server (각 로컬) ──→ PostgreSQL (GCP VM)
Claude Code (PC-3) ──┘
```

- **MCP 서버**: Claude Code가 stdio로 자동 실행. 에이전트가 도구를 호출하여 DB에 기록
- **DB 모드**: `KANBAN_DB_HOST` 환경변수 설정 여부로 자동 분기
  - 미설정 → SQLite 로컬 모드 (기본값, 설정 불필요)
  - 설정 → PostgreSQL 클라우드 모드 (여러 PC가 동일 DB 공유)
- **대시보드**: `session_board`(Claude Session Dashboard)의 '칸반' 탭이 같은 DB를 읽기 전용으로 조회하여 칸반보드 표시

---

## Quick Start

```bash
# 의존성 설치
cd agent-kanban-server
uv sync

# MCP 서버 → Claude Code가 자동 실행 (수동 실행 불필요)
# 대시보드 → session_board(Claude Session Dashboard)의 '칸반' 탭에서 조회

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

### 로컬 모드 (기본값, 설정 불필요)

각자의 PC에서 독립적인 SQLite DB로 실행. **환경변수 설정 불필요.**

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

### 클라우드 공유 모드 (PostgreSQL)

여러 PC의 Claude Agent가 동일한 GCP PostgreSQL DB를 공유하는 방식.
MCP 서버는 각 로컬에서 실행되며, DB만 클라우드에 위치한다.

**방법 A: `.env` 파일 사용 (권장)**

`agent-kanban-server/.env` 파일 생성:

```ini
KANBAN_DB_HOST=<gcp-vm-외부IP>
KANBAN_DB_PORT=5432
KANBAN_DB_USER=ai_board_user
KANBAN_DB_PASSWORD=<password>
KANBAN_DB_NAME=ai_board
```

mcp.json은 변경 불필요. `.env`는 `.gitignore`에 포함 권장.

**방법 B: mcp.json에 직접 설정**

```json
{
  "mcpServers": {
    "ai-board": {
      "command": "uv",
      "args": ["run", "python", "-m", "agent_kanban"],
      "cwd": "/path/to/agent-kanban-server",
      "env": {
        "KANBAN_DB_HOST": "<gcp-vm-외부IP>",
        "KANBAN_DB_PORT": "5432",
        "KANBAN_DB_USER": "ai_board_user",
        "KANBAN_DB_PASSWORD": "<password>",
        "KANBAN_DB_NAME": "ai_board"
      }
    }
  }
}
```

### GCP PostgreSQL 초기 설정

PostgreSQL이 설치된 GCP VM에서 1회 실행:

```bash
# DB 및 사용자 생성
sudo -u postgres psql
```
```sql
CREATE DATABASE ai_board;
CREATE USER ai_board_user WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE ai_board TO ai_board_user;
GRANT CREATE ON SCHEMA public TO ai_board_user;
```

기존 SQLite 데이터 이전 (선택):

```bash
cd agent-kanban-server
python scripts/migrate_sqlite_to_pg.py --dry-run  # 사전 확인
python scripts/migrate_sqlite_to_pg.py            # 실제 이전
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
# 프로젝트명

## 원칙
- `.claude/docs/kanban.md` 파일이 있는 경우에는 모든 대화 실행 시 반드시 참조할 것

## 금지사항
- `kanban.db` 및 마이그레이션 스크립트는 명시 요청 없이 수정 금지
- 완료조건에 없는 모호함은 추론으로 채우지 말고 사용자에게 질문할 것

## 워크플로우
- 기획: `/plan <요구사항>` — 인터뷰 → 완료조건 포함 태스크 분해 → 승인 → 보드 등록
- 실행: `/clear` 후 새 세션에서 `/team-run` — 구현 → 자체 QA → 리뷰 → Done 자율 순환
- 복원: `/resume` — 최신 handoff 노트 기준 컨텍스트 복원
- 회고: `/retro` — 보드 데이터로 리뷰 실효성·프로세스 마찰·우회 측정
```

`.claude/docs/kanban.md`에는 팀 ID·에이전트 ID를 기록해둔다 (아래 "팀 구성" 참조).
이 파일이 있어야 `/clear` 후에도 커맨드들이 ID를 다시 찾을 필요가 없다.

### 핵심 포인트

| 항목 | 설명 |
|------|------|
| kanban.md 강제 참조 | 매 대화마다 팀/에이전트 ID를 다시 묻지 않도록 강제 |
| 커맨드 4개로 워크플로우 고정 | 기획·실행·복원·회고 각각을 시스템 프롬프트가 아니라 명시적 커맨드로 분리 |
| 금지사항 명시 | DB 직접 수정, 모호함 추론 등 반복되는 실수를 규칙으로 차단 |

---

## Slash Commands (핵심 워크플로우)

`.claude/commands/`에 4개 커맨드가 있으며, 프로젝트 로컬이라 별도 등록 없이 자동 인식된다.
각 커맨드의 전체 로직은 해당 파일에 있다 — 아래는 역할 요약이다.

### /plan — 기획 (요구사항 → 태스크)

`.claude/commands/plan.md`. `$ARGUMENTS`로 받은 요구사항을 곧바로 분해하지 않는다:

1. **요구사항 인터뷰** (생략 불가): 범위·제약·검증 방법·추론이 필요한 지점을 확인 — 모호함을
   추론으로 채우지 않고 `AskUserQuestion`으로 확정받는다
2. **태스크 분해**: 태스크 = 순차 진행 중 리뷰 체크포인트(커밋 단위). 각 태스크에
   `[auto]`/`[human]` 태그가 붙은 완료조건을 명시한다
3. **사용자 승인** (게이트): 분해 결과를 표로 제시하고 승인받기 전에는 `create_task` 호출 금지
4. **계획 문서 저장 + 보드 등록**: `.claude/docs/plans/plan-YYYYMMDD-<주제>.md`에 "왜와 경계"를
   저장하고, 승인된 태스크만 `create_task`

### /team-run — 실행 (구현 → 자체 QA → 리뷰 → Done 자율 순환)

`.claude/commands/team-run.md`. `/plan`으로 등록된 태스크를 순차로(동시에 하나씩) 진행한다.
`/clear` 후 새 세션에서 시작하는 것을 전제로 — 의도(완료조건)와 상태(노트)가 전부 보드에
있어 이전 대화 없이도 이어갈 수 있다.

- 태스크별: 착수 → 구현 → 자체 QA(`[auto]` 조건을 실제로 실행해 검증) → handoff 노트 →
  커밋 → Reviewer 서브에이전트(신선한 컨텍스트로 diff만 보고 재검증) → 판정
- FAIL 시 Rejected → 수정 → 재검증을 자동 순환하되 `MAX_QA_LOOP`/`MAX_REVIEW_FAIL` 회수를
  넘으면 강제 정지(서킷브레이커)하고 사용자에게 보고
- `[human]` 조건은 사람만 확인 가능 — Review 상태로 대기시키고 `AskUserQuestion`으로 확인받은
  뒤에만 Done 처리 (자율 판정 금지)
- 사람 개입은 이 [human] 확인, 블로커, 반복 반려 시로 한정된다

### /retro — 회고 (데이터 기반 튜닝 + 교훈 승격)

`.claude/commands/retro.md`. 완료된 계획의 보드 데이터(+git log)로 리뷰 실효성(러버스탬프
비율), 프로세스 마찰(QA 루프·블로커·[human] 대기 빈도), 우회(보드 밖 커밋)를 측정해
`.claude/docs/retros/retro-YYYYMMDD.md`로 저장한다. handoff 노트의 서사 필드(문제와 해결/
버린 접근)에서 재발 방지 교훈을 추려 사용자 승인 후 `.claude/docs/lessons.md`에 한 줄
지시형으로 승격한다 (상한 20줄, 큐레이션 필수).

### /resume — 세션 복원

`.claude/commands/resume.md`. `get_board`로 InProgress 태스크를 찾고 **최신 handoff 노트를
최우선으로** 읽어 완료조건/완료한 것/남은 것/주의사항을 요약한다.

### `.claude/docs/lessons.md` — 반복 방지 장치

`/retro`가 승격한 교훈이 쌓이는 파일. `/plan`과 `/team-run`이 매 실행 시작 시 읽어 과거
사이클의 실수를 계획·구현 단계에서 미리 차단한다. DB가 아니라 파일인 이유: 사람이 직접
큐레이션(통합·삭제)하기 쉽고, git diff로 변경 이력이 보이며, 영구 규칙이 되면 CLAUDE.md로
승격하고 여기서 빼는 흐름이 자연스럽기 때문이다.

---

## 사용 시나리오

### 일상 작업 흐름

```
# 1. 새 요구사항 기획 (사람과 함께, 인터뷰 후 승인 게이트)
/plan "결제 API 에러 핸들링 개선"
   → 인터뷰 → 태스크 분해 표 제시 → 승인 → 계획 문서 저장 + 보드 등록

# 2. /clear로 기획 대화의 잡음을 끊고 새 세션에서 실행
/clear
/team-run
   → Todo 소진까지 태스크를 순차로: 구현 → 자체 QA → 커밋 → 리뷰 → Done
   → [human] 확인이 필요하면 그 자리에서 질문, 아니면 자율 진행
   → N_DONE개 Done마다 세션 지속 여부 확인 (컨텍스트 오염 방지)

# 3. 세션이 끊겼다면 (수동 /clear, 자동 정지, 다음 날 재개 등)
/resume
   → 최신 handoff 노트 기준으로 어디까지 했는지 복원

# 4. 계획 완료 후 회고
/retro
   → 리뷰가 실제로 잡은 결함, 자주 깨진 규칙, 튜닝 제안을 보고
   → 승인 시 lessons.md에 교훈 승격 + 보드에 [retro]/[lessons] 다이제스트 게시
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
get_task_detail(task-xxxxxxxx)  → 진행 중이던 작업의 노트 확인 (handoff 노트 우선)
```

> **`.claude/docs/kanban.md`에 Team ID / Agent ID를 기록해두면** `/clear` 후에도 커맨드들이
> ID를 다시 찾을 필요가 없다.

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

대시보드 뷰잉은 **`session_board`(Claude Session Dashboard)의 '칸반' 탭**으로 완전 이전되었다.
기존 `web.py`(:48080 FastAPI 정적 서빙 + 읽기 REST API)와 `agent-kanban-dashboard`(React) 프로젝트는 폐기되었다.

- session_board Express가 같은 칸반 DB를 **읽기 전용**으로 조회한다 (`/api/kanban/*`).
  db.py의 듀얼모드(SQLite/PostgreSQL) 쿼리를 Node로 미러링.
- 칸반 DB에 도달 불가한 환경에서는 '칸반' 탭이 노출되지 않는다 (fail-closed).
- MCP 서버(`server.py`)의 쓰기·읽기 도구는 그대로 유지된다 — 이 폐기는 뷰잉 서버에만 해당.

읽기 REST API(팀/보드/태스크/팀상태)는 session_board `/api/kanban/*`가 담당한다.

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
