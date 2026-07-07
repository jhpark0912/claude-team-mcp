# SPEC.md — AI-Board 대시보드 / 데이터 모델 재설계

- 작성일: 2026-07-07
- 상태: 설계 확정 (Phase 1 상세 / Phase 2 스텁)
- 근거 파일:
  - `agent-kanban-server/src/agent_kanban/db.py`
  - `agent-kanban-server/src/agent_kanban/server.py`
  - `commands/plan.md`, `commands/plan-run.md`, `commands/retro.md`

---

## 1. 배경과 문제 정의

### 1.1 현재 구조의 붕괴 진단

현재 AI-Board는 칸반 보드(Backlog / Todo / InProgress / Review / Done / Rejected)를 1차 메타포로 사용한다. 칸반은 원래 여러 작업자를 조율하는 도구다. 그런데 실제 작업자는 하나(단일 Claude 세션)다. 그 결과:

- InProgress 컬럼이 항상 1개 이하여서 "진행 중이냐 아니냐" 두 버킷으로 사실상 수렴한다.
- 모든 태스크가 프로젝트 보드에 납작하게 흩어져 있어 "왜 이 작업들을 묶었는가"(의도·경계)가 보이지 않는다.
- 태스크와 플랜 문서(`.claude/docs/plans/*.md`)가 디스크 파일과 DB로 이원화되어 있어 보드가 플랜 맥락을 모른다.
- team / agent 테이블 개념이 실제 흐름(단일 세션)과 불일치하여 설정 오버헤드만 발생한다.

### 1.2 목적 재정의 (확정)

AI-Board는 "AI 팀이 병렬로 작업하는 도구"가 아니다. 단일 개발자가 Claude 세션을 소모품으로 쓰는 환경에서 아래 세 가지를 달성하는 워크플로우 엔진이다.

1. **세션 인계**: 세션 간 자신에게 작업을 인계한다. (handoff 노트가 핵심)
2. **반복 실수 방지**: 과거 실수를 lessons로 증류해 다음 플랜에 주입한다.
3. **유저 인사이트**: 유저가 "지금 무엇이 진행 중이고, 왜 이렇게 됐는가"를 파악할 수 있다.

이 세 목적 어디에도 병렬 실행이나 멀티에이전트 조율은 필요하지 않다.

**team → project 전면 전환 (구현 완료)**: "팀"의 본질(여러 작업자 조율)이 단일 세션 흐름과 맞지 않으므로, 기존 `teams` 테이블을 `projects`로, `team_id`를 `project_id`로 전면 리네임한다. `create_team` 도구는 `init_project`(레포당 1회 get-or-create, 멱등)로 교체한다. `agents` 테이블은 데이터·인터페이스를 보존하되 소속 컬럼만 `project_id`로 리네임한다. 기존 kanban.db는 `_migrate_legacy_team_to_project` 마이그레이션으로 id 값을 보존한 채 자동 전환된다(멱등).

---

## 2. 설계 개요

### 2.1 계층 구조

```
Project (레포당 1개 = projects 테이블, 싱글턴. 기존 teams를 리네임)
 └─ Plan (의도 + 경계: goal, scope_in, scope_out) — plans.project_id로 매달림
     ├─ Task (작업 단위, 리뷰 체크포인트)
     │    └─ Journal (태스크별 서사 — handoff/progress 노트를 읽히는 형태로 렌더)
     │         └─ Live (활성 태스크의 실시간 이벤트 스트림 — Phase 2)
     ├─ PlanSummary (플랜 완료 시 자동 초안 → 사람 큐레이션 — Phase 2)
     └─ Lessons (전역 반복 방지 증류 — 기존 lessons.md와 연결)
 └─ 미분류 버킷 (plan_id = NULL인 태스크)
```

> **프로젝트 = 레포 1개 = kanban.db 1개(싱글턴)**: 기존 `teams` 테이블을 `projects`로 리네임해
> 그대로 사용한다(별도 테이블 신설 아님). 한 kanban.db 안에서 `projects`는 사실상 1행이다.
> `plans`는 `project_id`에 매단다.
> (대시보드는 여러 repo/DB를 프로젝트 목록으로 aggregate한다 — 그 레벨이 진짜 "프로젝트 목록"이다.)

### 2.2 뷰 정합 원칙

| 뷰 레벨 | 메타포 | 설명 |
|---------|--------|------|
| 프로젝트 뷰 | 칸반 | 플랜들이 planned / active / completed / blocked로 나뉜다. 진짜 WIP는 여기서 의미를 가진다. |
| 플랜 뷰 | 타임라인 + 칸반 하이브리드 | 플랜 내부의 태스크를 순서(position)와 상태로 본다. |
| 태스크 뷰 | 저널 (서사) | handoff / progress 노트가 "왜 이렇게 됐는가"의 서사로 렌더된다. |

칸반을 플랜 레벨에 올리면 "같은 시점에 active 플랜이 몇 개인가"가 진짜 WIP 지표가 된다. 태스크 레벨에서 칸반을 쓰면 단일 세션이라 컬럼이 붕괴한다.

### 2.3 Journal = 기존 노트의 렌더 뷰

Journal은 새로운 데이터 구조가 아니다. `notes` 테이블에 이미 있는 handoff / progress / review / blocker 노트를 "읽히는 서사"로 렌더링하는 **뷰 레이어**다.

- **신규 노트** (Phase 2 구조화 이후): `왜 / 완료한 것 / 검증 / 문제와 해결 / 버린 접근 / 계획과 달라진 점 / 변경 파일` 필드로 렌더.
- **과거 노트** (현재): 자유 텍스트 폴백 렌더. 파싱 시도 없음.

### 2.4 Event vs Handoff (개념 분리 — Phase 2 착수 후 구체화)

| 개념 | 성격 | 저장 방식 |
|------|------|-----------|
| Event | 흐르는 것, append-only 스트림 | 미래 `events` 테이블 (Phase 2) |
| Handoff | 굳는 것, 구조화 요약 | `notes` 테이블의 `note_type='handoff'` (현재) |

Live 뷰 = 활성 태스크의 이벤트 스트림 최소 정의. Phase 2 게이트 통과 후 구체화.

### 2.5 플랜 파생 상태

플랜의 상태는 **저장하지 않는다**. 읽을 때 계산(compute-on-read)한다. denorm 저장 금지(드리프트 차단).

**파생 4상태** (태스크 상태에서 계산):
- `planned`: 태스크가 하나도 InProgress / Review / Done이 아님
- `active`: 태스크 중 하나 이상이 InProgress 또는 Review
- `completed`: 모든 태스크가 Done (또는 Rejected)이고, archived_at / cancelled_at / on_hold_at이 없음
- `blocked`: 태스크 중 하나 이상이 `is_blocked = true`

**명시 3플래그** (운영자가 직접 설정):
- `archived_at`: 완료 후 아카이브된 시각 (NULL = 아카이브 안 됨)
- `cancelled_at`: 취소된 시각
- `on_hold_at`: 보류된 시각

**타임스탬프**:
- `started_at`: 첫 번째 태스크가 InProgress로 바뀐 시각 (자동 기록)
- `completed_at`: 마지막 태스크가 Done이 된 시각 (자동 기록)

---

## 3. 데이터 모델

### 3.1 Phase 1 상세 스키마

Phase 1에서 추가되는 테이블과 컬럼을 기술한다. `tasks` / `notes`는 변경하지 않는다(additive-only). `teams`→`projects`, `team_id`→`project_id` 리네임은 별도 레거시 마이그레이션(`_migrate_legacy_team_to_project`)이 `init_db`의 CREATE 이전에 1회 처리한다.

#### 신규 테이블: `schema_migrations`

```sql
-- SQLite
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TEXT DEFAULT (datetime('now'))
);

-- PostgreSQL
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMP DEFAULT NOW()
);
```

버전 추적 없이 `CREATE TABLE IF NOT EXISTS`로만 스키마를 관리하면 `ALTER TABLE`(컬럼 추가)을 반복 실행할 방법이 없다. `schema_migrations`가 있어야 "해당 마이그레이션이 이미 적용됐는지"를 확인하고 건너뛸 수 있다.

#### 신규 테이블: `plans`

프로젝트는 리네임된 `projects` 테이블(구 `teams`)이다(레포당 1개). `plans`는 `project_id`에 매단다.

```sql
-- SQLite
CREATE TABLE IF NOT EXISTS plans (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
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
);

-- PostgreSQL
CREATE TABLE IF NOT EXISTS plans (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id),
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
);
```

#### 기존 테이블 컬럼 추가: `tasks`

```sql
-- v3: plan_id 추가 (nullable — 기존 태스크는 NULL = 미분류)
ALTER TABLE tasks ADD COLUMN plan_id TEXT REFERENCES plans(id);

-- v4: position 추가 (플랜 내 태스크 순서)
ALTER TABLE tasks ADD COLUMN position INTEGER;
```

기존 태스크는 `plan_id = NULL`로 유지된다. 백필 없음. `plan_id = NULL`인 태스크는 "미분류 버킷"으로 취급한다.

#### 인덱스 추가

```sql
CREATE INDEX IF NOT EXISTS idx_tasks_plan_id ON tasks(plan_id);
CREATE INDEX IF NOT EXISTS idx_tasks_plan_position ON tasks(plan_id, position);
CREATE INDEX IF NOT EXISTS idx_plans_project_id ON plans(project_id);
```

> 참고: 리네임 마이그레이션은 구 `teams` 기준 인덱스(`idx_tasks_team_*`, `idx_agents_team_id`, `idx_plans_team_id`)를 DROP하고, `init_db`가 `project_id` 기준 인덱스를 재생성한다.

### 3.2 Phase 1 완성 후 스키마 전체 요약

| 테이블 | 상태 | 비고 |
|--------|------|------|
| `schema_migrations` | 신규 | 마이그레이션 버전 추적 |
| `projects` | 리네임 | 구 `teams`를 리네임 (id 값·데이터 보존) |
| `plans` | 신규 | 의도 + 경계 |
| `tasks` | 컬럼 추가 + 리네임 | `plan_id`, `position` 추가 (nullable) / `team_id`→`project_id` |
| `notes` | 변경 없음 | 기존 그대로 |
| `agents` | 컬럼 리네임 | `team_id`→`project_id`, 데이터 보존 |

### 3.3 Phase 2 목표 스키마 (스텁 — 게이트 통과 후 확정)

아래는 Phase 1 가치 검증 후에만 착수하는 스텁이다. 필드 이름·타입은 Phase 2 설계 시점에 확정한다.

```
-- Phase 2 후보 (미확정)
notes 테이블 note_type에 'qa_fail' 추가
  → SQLite: 테이블 재빌드 필요 (CHECK 제약 변경)
  → PostgreSQL: CHECK 제약 DROP 후 ADD

plan_summaries 테이블 (신규)
  → 필드 후보: plan_id, outcome, key_problems, notable, follow_ups, created_at
  → 자동 초안 트리거 조건 미확정

events 테이블 (신규, append-only)
  → Live 뷰의 데이터 소스
  → 스키마 미확정
```

---

## 4. 마이그레이션 방안

### 4.1 5원칙

1. **Additive-only + nullable**: 기존 컬럼·데이터를 변경하지 않는다. `tasks.plan_id`는 nullable로 ADD. 기존 태스크는 `plan_id = NULL = 미분류`로 자연 편입된다. 롤백 시 컬럼 DROP만으로 원상 복구 가능.

2. **백필 없음 + 폴백 렌더**: 과거 notes의 자유 텍스트를 구조화된 필드로 파싱하지 않는다. 파싱은 취약하다(`참고:` 레이블 등 포맷이 불일치함). 저널 뷰는 신규(구조화)와 과거(자유 텍스트) 두 경로로 렌더한다.

3. **듀얼 DB 동시 작성**: 모든 DDL을 SQLite / PostgreSQL 양쪽에 작성한다. Phase 2의 `note_type`에 `qa_fail` 추가는 CHECK 제약 변경이므로 비용이 다르다(SQLite: 테이블 재빌드, PG: DROP/ADD). 이 비용을 Phase 2 착수 전에 명시한다.

4. **schema_migrations 버전 러너 신설**: `IF NOT EXISTS`만으로는 `ALTER TABLE` 멱등성을 보장할 수 없다. 버전 러너가 `schema_migrations` 테이블을 확인하고, 적용되지 않은 마이그레이션만 실행한다.

5. **플랜 상태 저장 안 함**: 파생 상태는 compute-on-read로만 계산한다.

### 4.2 Phase 1 마이그레이션 스텝 (실제 DDL)

러너는 `schema_migrations` 테이블의 `version` 컬럼을 확인하고, 해당 버전이 없을 때만 실행한다.

```
(레거시) teams→projects / team_id→project_id 리네임 (init_db CREATE 이전, 멱등)
(사전)  CREATE schema_migrations (러너 루프 이전에 무조건 생성, 위 §3.1 DDL 참조)
v1  CREATE plans
v2  ALTER tasks ADD COLUMN plan_id TEXT REFERENCES plans(id)
v3  ALTER tasks ADD COLUMN position INTEGER
```

> `projects`는 리네임 마이그레이션 또는 `init_db`의 `CREATE TABLE IF NOT EXISTS`로 준비되므로 버전 러너 대상이 아니다. 러너는 `plans` 신설과 `tasks` 컬럼 추가만 담당한다.

**SQLite v2 실행 예시 (러너 내부 로직):**
```python
if not _migration_applied(conn, 2):
    conn.execute("ALTER TABLE tasks ADD COLUMN plan_id TEXT REFERENCES plans(id)")
    _record_migration(conn, 2, "tasks_add_plan_id")
    conn.commit()
```

**PostgreSQL v2 실행 예시:**
```python
if not _migration_applied(conn, 2):
    _exec(conn, "ALTER TABLE tasks ADD COLUMN plan_id TEXT REFERENCES plans(id)")
    _record_migration(conn, 2, "tasks_add_plan_id")
    conn.commit()
```

기존 tasks 데이터: `plan_id = NULL` 유지. 백필 없음.
`projects`(구 `teams`) / `agents` 테이블: 리네임 마이그레이션 외 데이터 변경 없음.

### 4.3 마이그레이션 러너 설계

`db.py`의 `init_db()` 함수를 확장하거나, 별도 `migrate_db()` 함수로 분리한다. 분리를 권장한다(관심사 명확화).

```
migrate_db(conn):
  1. schema_migrations 테이블이 없으면 생성 (v0)
  2. 현재 적용된 최대 버전 조회
  3. v1 ~ vN 순서대로: 미적용 버전만 실행
  4. 각 실행 후 schema_migrations에 기록 + commit
```

`projects`(리네임 또는 `CREATE TABLE IF NOT EXISTS`)와 `plans`(`CREATE TABLE IF NOT EXISTS`)는 러너 없이도 안전하다. 기존 테이블의 컬럼 추가(`plan_id`, `position`)만 러너가 담당한다.

### 4.4 롤백 전략

Phase 1은 additive-only이므로 롤백은 단순하다.

```sql
-- SQLite: 컬럼 DROP 불가 → 테이블 재빌드 필요 (비용 높음)
-- PostgreSQL: ALTER TABLE tasks DROP COLUMN plan_id;
--             ALTER TABLE tasks DROP COLUMN position;
--             DROP TABLE plans;
--             DROP TABLE projects;
```

SQLite에서 컬럼 DROP이 불가능한 점은 수용 가능한 제약이다. Phase 1 변경이 additive이므로 롤백 시나리오 자체가 드물다.

---

## 5. 대시보드 뷰

### 5.1 프로젝트 뷰 (최상위) — 플랜 칸반

```
┌────────────────────────────────────────────────────────────────────┐
│  프로젝트: claude-team-mcp                                           │
│                                                                      │
│  planned(2)    active(1)       completed(3)    blocked(0)            │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐                         │
│  │DB 재설계  │  │대시보드 통합│  │web.py 폐기│                        │
│  │goal: ... │  │goal: ...  │  │완료       │                         │
│  │태스크 5개 │  │태스크 8개  │  │          │                         │
│  └──────────┘  └────────────┘  └──────────┘                         │
│                                                                      │
│  미분류 버킷 (plan_id = NULL): 태스크 3개                             │
└────────────────────────────────────────────────────────────────────┘
```

플랜 카드를 클릭하면 플랜 뷰로 진입한다.

### 5.2 플랜 뷰 (중간) — 태스크 타임라인 + 칸반 하이브리드

```
┌─────────────────────────────────────────────────────────────────────┐
│  플랜: 대시보드 통합                                                    │
│  goal: session_board에 칸반 탭을 네이티브 통합                          │
│  scope_in: ...   scope_out: ...                                       │
│  상태: active  |  started_at: 2026-07-01  |  태스크 8/10 완료          │
│                                                                       │
│  타임라인 (position 순)          상태 요약                              │
│  #1 [Done]  스펙 문서화          Backlog 0 / Todo 1 / InProgress 1    │
│  #2 [Done]  DB 리더 서비스       Review 0 / Done 8 / Rejected 0       │
│  #3 [InProgress] 라우트 5종 ◄── 활성 태스크                            │
│  #4 [Todo]  컴포넌트 이식                                              │
│  #5 [Backlog] 통합 검증  (선행: #4)                                    │
│                                                                       │
│  태스크 #3 클릭 → 저널 뷰 (서사)                                        │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.3 태스크 저널 뷰 (하단) — 서사 렌더

```
┌─────────────────────────────────────────────────────────────────────┐
│  #3 라우트 5종 구현  [InProgress]                                      │
│                                                                       │
│  완료조건:                                                             │
│  [auto] GET /api/kanban/board/:projectId 응답 200                     │
│  [human] 대시보드에서 칸반 탭 정상 렌더 확인                              │
│                                                                       │
│  저널 (시간순)                                                          │
│  ──────────────────────────────────────────────────────────────────  │
│  [progress]  2026-07-03 10:15  착수 계획: /api/kanban/* 5종 구현 예정  │
│  [progress]  2026-07-03 11:30  QA-FAIL 1회차: board 응답 is_blocked   │
│                                  불리언 캐스팅 누락                      │
│  [handoff]   2026-07-03 14:00  완료한 것: board/tasks/team-status 구현 │
│                                  문제와 해결: PG datetime Z suffix      │
│                                  변경 파일: kanban.js, kanbanDb.js     │
│  ──────────────────────────────────────────────────────────────────  │
│  과거 노트 (자유 텍스트 폴백)                                            │
│  [system]   2026-06-15  Task created by system: ...                  │
└─────────────────────────────────────────────────────────────────────┘
```

**렌더 경로 분기:**
- `note_type = 'handoff'`이고 필드 구조(`완료한 것:`, `문제와 해결:` 등)가 감지되면 → 구조화 렌더
- 그 외(과거 노트, 자유 텍스트) → 원문 그대로 렌더 (폴백)

### 5.4 Live 뷰 (Phase 2 스텁)

활성 태스크의 실시간 이벤트 스트림. Phase 2 착수 후 구체화한다. Phase 1에서는 "가장 최근 progress 노트"를 라이브 최신 상태로 표시하는 것으로 대체한다.

---

## 6. 커맨드 변경점

### 6.1 `/plan` (plan.md)

**추가:**
- Phase 4에서 `create_task` 시 `plan_id`와 `position`을 함께 전달한다.
- 계획 문서 저장(`plans/plan-YYYYMMDD-<주제>.md`)과 동시에 `plans` 테이블에도 플랜 레코드를 생성한다.
- `goal`, `scope_in`, `scope_out`을 DB에 저장한다(인터뷰 결과 → DB → 대시보드 표시).

**제거:**
- "팀" 프레이밍 없음. `create_team` → `init_project`(레포당 1회 get-or-create). 기존에 kanban.md에 프로젝트 ID가 등록돼 있으므로 해당 ID를 그대로 사용한다.

**변경 없음:**
- 인터뷰 절차, 태스크 분해 규칙, 사용자 승인 게이트.

**구체적 Phase 4 변경:**
```
기존: create_task(project_id, title, description, priority)
신규: create_task(project_id, title, description, priority, plan_id=<신규 플랜 ID>, position=N)
```

`plan_id`는 `/plan` 실행 시 생성한 플랜 레코드의 ID다. `position`은 태스크 분해 순서(1부터 시작).

### 6.2 `/plan-run` (plan-run.md)

**추가:**
- Phase 0 복원 시 `get_board` 대신(또는 병행해서) 활성 플랜의 태스크를 `position` 순으로 조회한다.
- handoff 노트 작성 후 `plan_id`가 있는 태스크는 저널 뷰에 자동 표시된다.

**제거:**
- "팀" 프레이밍 없음. 내부 로직에서 `project_id`를 파라미터로 사용하며, 커맨드 설명에서 "팀"이라는 표현 제거.
- Reviewer 서브에이전트는 유지한다(유일하게 격리된 서브에이전트).

**변경 없음:**
- handoff 노트 스키마(7개 필드): 이것이 저널의 원료다. 형식 변경 없음.
- QA-FAIL 노트 규칙, flow-blocked 계측, MAX_QA_LOOP / MAX_REVIEW_FAIL.

**커맨드 문서 "팀 프레이밍 제거" 구체적 표현:**
```
기존: "칸반보드의 태스크를 순차 실행한다. 구현 → 자체 QA → 리뷰 → Done을 자율 순환하며..."
신규: "보드의 태스크를 순차 실행한다. 구현 → 자체 QA → 리뷰 → Done을 자율 순환하며..."
```

### 6.3 `/retro` (retro.md)

**추가:**
- 회고 발행 시 `[retro]` 태스크를 생성할 때 `plan_id`를 지정하면 해당 플랜의 저널 뷰에 회고가 연결된다.
- Lessons 승격 후 `PlanSummary` 연결은 Phase 2 스텁.

**변경 없음:**
- 데이터 수집, 분석 항목(리뷰 실효성 / 프로세스 마찰 / 우회 측정).
- lessons.md 승격 규칙, retro 파일 저장.

---

## 7. Phase 2 스텁 (게이트 통과 후 확정)

**Phase 2 착수 금지 조건**: Phase 1 배포 후 "유저가 저널 뷰를 실제 소비하는가"가 검증되기 전에는 Phase 2에 착수하지 않는다. 검증 기준은 §8의 가치 검증 게이트에 정의한다.

### 7.1 구조화 handoff 필드

현재 handoff 노트는 자유 텍스트(관례적 필드 형식)다. Phase 2에서는 DB 컬럼으로 구조화한다.

후보 스키마 (미확정):
```
notes 또는 신규 handoff_entries 테이블:
  why TEXT
  completed TEXT
  verification TEXT
  problem_solution TEXT
  discarded TEXT
  plan_deviation TEXT
  changed_files TEXT
```

### 7.2 note_type `qa_fail` 추가

현재 `notes.note_type` CHECK 제약: `('progress','blocker','handoff','review','system')`.
Phase 2에서 `qa_fail`을 추가하면 CHECK 제약을 변경해야 한다.

비용:
- SQLite: `ALTER TABLE` CHECK 변경 불가 → 테이블 재빌드(`CREATE TABLE new → INSERT SELECT → DROP → RENAME`) 필요
- PostgreSQL: `ALTER TABLE notes DROP CONSTRAINT <name>; ALTER TABLE notes ADD CONSTRAINT ... CHECK(...)`

이 비용을 Phase 2 착수 전 사용자에게 명시하고 승인받는다.

### 7.3 PlanSummary 자동 초안

플랜의 모든 태스크가 완료될 때 (`completed_at` 기록 시점) 아래 신호에서 초안을 생성한다.

- `note_type = 'qa_fail'`인 노트 → `key_problems` 후보
- `note_type = 'blocker'`인 노트 → `key_problems` 후보
- handoff 노트의 `problem_solution` / `discarded` / `plan_deviation` 필드 → `notable` 후보

초안은 사람 큐레이션이 필요하다. 자동 확정 없음.

**Handoff(태스크별) → PlanSummary(플랜 전체) → Lessons(전역 증류)** 세 층은 겹치지 않고 흐른다.

### 7.4 Event / Handoff 분리

Phase 2에서 `events` 테이블(append-only)을 신설해 Live 뷰를 지원한다. 스키마 미확정.

---

## 8. 리스크 및 검증 게이트

### 8.1 리스크 목록

| ID | 리스크 | 영향 | 대응 |
|----|--------|------|------|
| R-01 | **계측 규율 의존** | handoff / QA-FAIL 노트를 plan-run이 성실히 기록하지 않으면 저널·요약의 품질이 0에 수렴한다. 저널 뷰는 데이터가 있어야 의미가 있다. | plan-run.md의 "계측 필수" 규칙을 유지. /retro에서 handoff 노트 스키마 준수율을 계속 측정. |
| R-02 | **유저 소비 미검증** | 저널 뷰를 만들어도 유저가 실제로 보지 않으면 Phase 2의 모든 복잡도는 낭비다. | Phase 1 가치 검증 게이트(§8.2) 통과 전 Phase 2 착수 금지를 SPEC에 못박는다. |
| R-03 | **듀얼 DB CHECK 변경 비용** | Phase 2에서 `qa_fail` 타입 추가 시 SQLite 테이블 재빌드가 필요하다. WAL 모드 + 기존 데이터 포함 시 리스크 존재. | Phase 2 착수 전 실제 비용을 측정하고 사용자 승인을 받는다. |
| R-04 | **SQLite 컬럼 DROP 불가** | Phase 1 롤백 시 `plan_id` / `position` 컬럼을 DROP할 수 없다. | Additive-only 원칙으로 수용. 롤백 필요성 자체를 최소화하는 설계. |
| R-05 | **마이그레이션 러너 신뢰성** | `schema_migrations` 기록과 실제 스키마 상태가 불일치하면 러너가 이미 적용된 마이그레이션을 건너뛰거나 재실행할 수 있다. | 각 마이그레이션을 멱등하게 작성(가능한 경우 IF NOT EXISTS). 적용 전 상태를 SELECT로 검증. |

### 8.2 가치 검증 게이트 (Phase 1 → Phase 2 착수 조건)

Phase 1 배포 후 다음 기준이 모두 충족될 때만 Phase 2 착수를 허용한다.

**정량 기준 (측정 가능):**
- [ ] `/retro`에서 "저널 뷰 관련 언급"이 1회 이상 보고됨 (유저가 실제로 사용)
- [ ] 활성 플랜이 plan_id와 함께 태스크를 가진 상태로 1 사이클(플랜 생성 → 완료) 이상 실행됨
- [ ] `schema_migrations` 러너가 SQLite / PostgreSQL 양쪽에서 정상 동작 확인됨

**정성 기준 (유저 판단):**
- [ ] "플랜 칸반 뷰가 태스크 칸반 뷰보다 WIP 파악에 유용하다"고 유저가 판단

이 게이트는 추론으로 통과하지 않는다. 유저가 명시적으로 승인해야 한다.

### 8.3 Phase 1 완료 정의

| 항목 | 검증 방법 |
|------|-----------|
| `schema_migrations` 테이블 생성 | SQLite에서 `.schema schema_migrations` 확인 |
| `projects` / `plans` 테이블 생성 | 동일 |
| `tasks.plan_id` 컬럼 추가 | `PRAGMA table_info(tasks)` 확인 |
| `tasks.position` 컬럼 추가 | 동일 |
| 기존 태스크 `plan_id = NULL` 유지 | `SELECT COUNT(*) FROM tasks WHERE plan_id IS NULL` > 0 |
| 마이그레이션 러너 멱등 실행 | 러너를 2회 실행해도 오류 없고 `schema_migrations`에 중복 기록 없음 |
| 기존 MCP 도구 정상 동작 | `uv run pytest tests/ -v` 통과 |

---

## 부록 A. 현재 MCP 도구 목록

Phase 1은 데이터 모델 변경과 team→project 리네임을 포함한다. 시그니처 변경은 아래 표의 "Phase 1 변경" 열 참조.

| 도구 | 역할 | Phase 1 변경 |
|------|------|-------------|
| `create_task` | 태스크 생성 | `plan_id`, `position` 파라미터 추가 (선택적) |
| `update_task_status` | 상태 변경 | 변경 없음 |
| `assign_task` | 담당자 할당 | 변경 없음 |
| `add_note` | 노트 추가 | 변경 없음 |
| `flag_blocker` | 블로커 설정 | 변경 없음 |
| `get_board` | 보드 조회 | 변경 없음 (plan 필터 파라미터 추가는 Phase 2) |
| `get_task_detail` | 태스크 상세 | 변경 없음 |
| `get_project_status` | 프로젝트 상태 | 구 `get_team_status` 리네임 |
| `init_project` | 프로젝트 준비 | 구 `create_team` → get-or-create(멱등)로 교체 |
| `add_agent` | 에이전트 추가 | `project_id` 파라미터로 리네임 |

신규 MCP 도구 추가 (Phase 1):
- `create_plan(project_id, title, goal, scope_in, scope_out)` → `plans` 테이블에 저장
- `get_plan(plan_id)` → 플랜 + 파생 상태 + 태스크 목록 반환
- `list_plans(project_id)` → 프로젝트별 플랜 목록 + 파생 상태

---

## 부록 B. 트레이드오프 요약

### [P-01] 플랜 상태: compute-on-read vs denorm 저장

| | compute-on-read (채택) | denorm 저장 |
|--|------------------------|------------|
| 장점 | 드리프트 없음. 태스크 상태와 항상 정합. | 조회 쿼리 단순. |
| 단점 | 플랜 목록 조회 시 태스크 집계 JOIN 필요. | 태스크 상태 변경 시 플랜 상태도 갱신해야 함. 동기화 실패 리스크. |
| 결론 | 단일 사용자 규모에서 compute-on-read 성능 문제 없음. 정합성 우선. | |

### [P-02] 저널: 신규 테이블 vs 기존 notes 렌더 뷰

| | 기존 notes 렌더 뷰 (채택) | 신규 테이블 |
|--|--------------------------|------------|
| 장점 | 마이그레이션 없음. 기존 데이터 그대로. 구현 최소화. | 구조화 쿼리 용이. |
| 단점 | 과거 노트 구조화 불가. 렌더 로직 복잡. | 기존 notes와 이중화. 마이그레이션 비용. |
| 결론 | Phase 1은 렌더 뷰로 시작. Phase 2에서 필요 시 분리. | |

### [P-03] 마이그레이션: schema_migrations 러너 vs 수동 DDL

| | schema_migrations 러너 (채택) | 수동 DDL |
|--|------------------------------|---------|
| 장점 | 멱등 실행 보장. 버전 추적. CI/배포 자동화 가능. | 구현 단순. |
| 단점 | 러너 코드 신뢰성 의존. 테이블 불일치 리스크. | ALTER TABLE 반복 실행 시 오류. 버전 관리 불가. |
| 결론 | ALTER TABLE이 1개 이상이면 러너 없이 운영할 수 없음. | |
