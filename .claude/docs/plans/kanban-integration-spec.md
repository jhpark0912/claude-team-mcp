# SPEC: 칸반 대시보드 → session_board 네이티브 통합

- 태스크: `task-Nu4jNhME` (통합 스펙 문서화 / 아키텍처 확정)
- 프로젝트: `team-Aa3xGjTv` (AI-Board 통합, id 값은 리네임 전 그대로 보존)
- 작성일: 2026-07-06
- 상태: **사용자 승인 대기**

## 0. 배경과 경계 (왜)

MCP 칸반 대시보드(`agent-kanban-dashboard`, React+shadcn)를 별도로 띄우지 않고,
이미 상시 사용하는 `05.session_board`(Claude Session Dashboard) 한 화면의 **'칸반' 탭**으로
네이티브 포팅한다. 백엔드는 **완전 이전**한다 — session_board Express가 칸반 DB를 직접 읽는다.
MCP 서버(`server.py`)는 쓰기 담당으로 분리 유지하고, 대시보드 뷰잉 책임만 이전한다.

**DB 공유:** Postgres를 Supabase로 호스팅해 클라우드 공유. 목적은 **단일 사용자의 다기기 동기화**
(같은 업무를 여러 컴퓨터에서 이어서). 멀티유저 협업이 아니다.

**전역 스코프밖 (모든 후속 태스크 공통):**
- **인증 / RLS / 유저 격리 금지.** 단일 사용자 전제이므로 스코프에 넣지 않는다.
- **쓰기 API 금지.** session_board 측은 **읽기 전용**. 쓰기는 MCP 도구가 담당.
- `.env`(Supabase 접속정보)는 **커밋 금지·마스킹**. `.env.example`만 템플릿으로 커밋.
- 칸반 관련 코드는 session_board 기존 4개 탭 동작·스타일을 **회귀시키지 않는다**.

**대상 레포:** 구현 대부분은 `C:\Exception\0.STUDY\05.session_board`.
`web.py` 폐기(task-QY1WXQQI)만 `00.claude-team-mcp` 레포.

---

## 1. API 계약 — `/api/kanban/*` (읽기 전용 5종)

session_board Express(`server/src/routes/*.js`, `/api/*` 프리픽스, 포트 3001)에
`kanban.js` 라우트를 추가하고 `server/src/index.js`에 `/api/kanban`으로 마운트한다.
프론트 `useKanban.ts`의 `API_BASE`는 `/api` → `/api/kanban`으로 변경한다(task-VOOp_2aq).

응답 스키마는 `agent-kanban-dashboard/src/types/kanban.ts`와 **1:1 동일**해야 하며,
쿼리 로직은 `agent-kanban-server/src/agent_kanban/db.py`를 **정확히 미러링**한다.

| # | 메서드·경로 | 미러 대상 | 응답 타입 |
|---|-------------|-----------|-----------|
| 1 | `GET /api/kanban/projects` | `list_projects` (`SELECT id,name,created_at FROM projects ORDER BY created_at ASC`) | `Project[]` |
| 2 | `GET /api/kanban/board/:projectId` | `get_board(conn, project_id)` | `BoardData` |
| 3 | `GET /api/kanban/tasks/:taskId` | `get_task_detail(conn, task_id)` | `TaskDetail` |
| 4 | `GET /api/kanban/project-status/:projectId` | `get_project_status(conn, project_id, activity_hours=24)` | `ProjectStatus` |
| 5 | `GET /api/kanban/available` | (신규) DB 도달 감지 | `{ available: boolean }` |

**쿼리 재현 시 반드시 지킬 것 (db.py와 동일):**
- **board**: 서브쿼리로 `note_type != 'system'`인 **최신 노트 1건**을 `latest_note`로 조회
  (없으면 필드 생략), `LEFT JOIN agents`로 `assigned_to = "{name} ({role})"`(없으면 null),
  `ORDER BY t.priority DESC, t.created_at ASC`, 상태별 `counts`, `wip_status`(config.wip_limits 기준
  `"{count}/{limit}"`, 없으면 빈 객체), `is_blocked`는 불리언으로 캐스팅.
  ※ `priority DESC`는 db.py의 사전식 정렬 그대로 **동일 재현**한다(의미순 재정렬 금지 — 정렬은 프론트 책임).
- **task detail**: `tasks JOIN projects LEFT JOIN agents`, notes는 `created_at ASC`,
  노트 agent 표기는 `"{name} ({role})"` / `"system"` / 원본 `agent_id` 순 폴백.
- **project-status**: 상태별 `summary`(GROUP BY status), 에이전트 워크로드
  (`LEFT JOIN tasks ... GROUP BY agent`, `in_progress`·`total`), `blockers`(is_blocked인 태스크),
  `recent_activity`(`note_type='system'` + 최근 `activity_hours`시간, 최신순 LIMIT 20,
  content에 `"Status changed"` 포함 시 action=`status_change` 아니면 `update`).
- **datetime 직렬화**: 모든 시각은 **UTC `Z` suffix**(`YYYY-MM-DDTHH:MM:SSZ`).
  SQLite는 이미 이 형식으로 저장됨. **Postgres `TIMESTAMP`는 Node에서 Z suffix로 정규화**해야 함
  (web.py의 `_json_default`가 하던 역할). Date → `.toISOString().replace(/\.\d+Z$/, 'Z')` 등.
- **플레이스홀더 차이**: PG는 `$1,$2...`(node-postgres), SQLite는 `?`(better-sqlite3).
  db.py의 `_exec`가 `%s`를 분기 처리하듯, 라우트에서 드라이버별로 처리한다.
- **에러**: 프로젝트/태스크 미존재 시 **404**(web.py의 `NotFoundError` → `HTTPException(404)` 대응).

---

## 2. DB 도달 감지 + 조건부 탭 노출

### 2.1 DB 리더 서비스 (task-Lld_mySw)
`server/src/services/kanbanDb.js` 신규. db.py의 듀얼모드를 Node로 미러링.
의존성 추가: `pg`(node-postgres) + `better-sqlite3`. 연결은 **readonly**로 연다.

**분기 규칙 (db.py `_use_pg()`와 동일):**
- `KANBAN_DB_HOST` 환경변수 **설정 시** → Postgres/Supabase
  (`KANBAN_DB_PORT`/`USER`/`PASSWORD`/`NAME`, 기본값은 db.py와 동일하게).
- **미설정 시** → 로컬 SQLite. 경로는 `KANBAN_DB_PATH` 우선,
  없으면 기본 탐지(`00.claude-team-mcp/agent-kanban-server/kanban.db`).

**`available()` 헬퍼:** DB 도달 가능 여부를 불리언으로 반환.
- PG 모드: env가 채워져 있고 커넥션/`SELECT 1`이 성공하면 true.
- SQLite 모드: 대상 `.db` 파일이 **실제로 존재**하면 true(파일 없으면 false).
- 완료조건: 도달 시 커넥션 반환, 미도달 시 감지 가능, **PG/SQLite 양쪽에서 `projects` 1건 조회 성공**.

### 2.2 조건부 탭 노출 — "MCP/DB 없으면 메뉴 미노출" (task-46apWJUG)

**요구:** MCP 칸반 DB에 도달할 수 없는 환경(= MCP를 안 쓰는 사용자/머신)에서는
'칸반' 메뉴 자체가 **아예 나타나지 않아야** 한다. 탭을 눌러 빈 화면·에러를 보는 일이 없어야 한다.

**"MCP/DB 없음"의 정의(§2.1 `available()`와 동일):**
Supabase env(`KANBAN_DB_HOST`)도 없고 로컬 `kanban.db` 파일도 없으면 → `available: false`.

**노출 게이트 (3중):**
1. **탭 렌더 게이트:** 앱 최초 로드 시 `GET /api/kanban/available` 1회 조회.
   `available === true`일 때만 `Layout.jsx`의 NavTab 배열에 '칸반' 항목을 **조건부로 push**한다.
   `false`면 NavTab을 만들지 않는다 → 기존 4개 탭만 표시(레이아웃 폭 변화 없음).
2. **라우트 가드:** `/kanban` 라우트도 `available === true`일 때만 등록한다.
   URL을 직접 입력해 진입하더라도 `available: false`면 라우트가 없어 기존 리다이렉트/404 처리로 흘러간다.
3. **조회 실패 = 없음 취급:** `/api/kanban/available` 요청 자체가 실패(네트워크·서버 미기동)해도
   `available: false`로 간주(fail-closed) → 메뉴 미노출. 즉 **의심스러우면 숨긴다.**

**상태 처리:** available 조회 결과가 확정되기 전(로딩)에는 칸반 탭을 **렌더하지 않는다**
(깜빡임 방지). 결과 도착 후 true면 그때 탭이 나타난다.

이로써 칸반 DB/MCP가 없는 환경에서도 session_board는 **기존 그대로** 정상 동작하고,
칸반 관련 UI는 흔적조차 노출되지 않는다.

---

## 3. 테마 병합 전략 (shadcn 토큰 ↔ session_board CSS 변수)

session_board는 **Tailwind 4**(`@tailwindcss/vite`, 별도 config 파일 없음, CSS-first),
`client/src/index.css`에서 CSS 변수로 테마를 구동한다. 테마 전환은 `<html>`의
`data-theme` 속성(localStorage `dashboard-theme`)으로 dark/light를 토글한다.

포팅되는 shadcn 컴포넌트는 `--background`/`--foreground`/`--card`/`--muted`/
`--muted-foreground`/`--border`/`--primary`/`--accent`/`--radius` 등의 토큰과
Tailwind 유틸(`bg-muted`, `text-muted-foreground`, `rounded-lg` 등)을 쓴다.

**병합 원칙: shadcn 토큰의 원본 다크값을 복사하지 않고, session_board 기존 변수를 참조하도록 재정의한다.**
그러면 `data-theme` 전환 시 session_board 변수(`--bg` 등)가 알아서 뒤집히므로
dark/light를 이중 정의할 필요 없이 자동 연동된다.

**매핑(초안, 구현 태스크에서 미세조정 가능):**

| shadcn 토큰 | session_board 변수 |
|-------------|--------------------|
| `--background` | `var(--bg)` |
| `--foreground` | `var(--tx)` |
| `--card` / `--popover` | `var(--s1)` / `var(--s2)` |
| `--muted` | `var(--s2)` |
| `--muted-foreground` | `var(--tx2)` (더 흐리게: `var(--mt)`) |
| `--border` / `--input` | `var(--bd)` |
| `--primary` | `var(--ac)` |
| `--accent` | `var(--ac2)` |
| `--ring` | `var(--ac)` |
| `--radius` | `var(--r)` |

### 3.1 기존 UI 비침범 가드레일 (필수)

테마 병합이 session_board 기존 4개 탭(timeline/analytics/reports/monitor)을 **한 픽셀도**
바꾸지 않도록 아래를 계약으로 삼는다. 구현·리뷰 시 이 항목들을 체크한다.

- **전역 토큰 재정의 금지:** shadcn 토큰(`--background`/`--muted` 등)을 전역 `:root`나
  `[data-theme]`에 정의하지 않는다. 반드시 **칸반 서브트리 래퍼**(`.kanban-scope { ... }` 또는
  `/kanban` 페이지 루트 엘리먼트)에만 스코프한다. 토큰이 상위로 새면 기존 탭에 영향을 준다.
- **기존 변수 값 변경 금지:** `index.css`의 기존 변수(`--bg`/`--tx`/`--ac`/`--s1~3`/`--bd`/
  `--gn`·`--yw`·`--rd`·`--pr`/`--r`·`--rs`·`--rx` 등)의 **값을 수정하지 않는다.**
  칸반 토큰은 이 변수들을 **읽기만**(`var(--bg)`) 한다 — 단방향 참조.
- **기존 컴포넌트/CSS 파일 미변경:** `Layout.jsx`는 칸반 NavTab **추가**(조건부 push)만 하고
  기존 탭 마크업·클래스는 건드리지 않는다. `App.jsx`는 `/kanban` 라우트 **추가**만 한다.
  기존 페이지·컴포넌트 파일은 수정하지 않는다.
- **Tailwind 유틸 전역오염 방지:** 포팅 컴포넌트가 쓰는 유틸(`bg-muted` 등)이
  기존 탭 요소에 적용되지 않도록, 칸반 마크업은 전부 `.kanban-scope` 하위에만 존재한다.
  기존 탭은 Tailwind 유틸을 거의 안 쓰므로(인라인·기존 CSS변수 기반) 충돌면이 작다 —
  단 `@theme inline` 등록으로 **새 유틸을 생성**할 뿐, 기존 클래스 의미를 바꾸지 않음을 확인한다.
- **폰트/줌·radius 회귀 확인:** `data-fontsize` 줌, 기존 radius(`--r` 등) 적용이 유지되는지
  4개 탭에서 육안 확인(task-cJTeQp2t·task-O1aUOIlJ 검증 항목).

### 3.2 충돌 격리 요약
- shadcn 토큰 정의는 전역 `:root`가 아니라 **칸반 서브트리 스코프**
  (`.kanban-scope { ... }` 래퍼 또는 `/kanban` 페이지 루트)에 둔다 —
  기존 4개 탭의 스타일에 토큰이 새지 않게 한다.
- **Tailwind 4 연동:** 위 토큰을 `@theme inline { --color-background: var(--background); ... }`로
  등록해 `bg-background`·`text-muted-foreground` 등의 유틸이 생성되게 한다(shadcn+Tailwind4 표준).
- `text-red-400`/`bg-red-500/15` 같은 **리터럴 팔레트 유틸**은 Tailwind 기본 팔레트로 해결됨 — 별도 매핑 불필요.
- **인프라 의존성(task-cJTeQp2t):** `class-variance-authority`·`clsx`·`tailwind-merge`·
  `lucide-react`·radix 프리미티브·`tw-animate-css`·`react-markdown` 추가.
  `vite.config`에 **`@` alias**(→ `client/src`) 추가. session_board는 tsc 없이 Vite만 쓰므로
  **`.tsx`는 런타임 트랜스파일**로 동작(tsconfig 불필요).
- **검증 기준(task-cJTeQp2t 완료조건):** 샘플 shadcn 컴포넌트(button 등)가
  기존 4개 탭 스타일을 **깨지 않고** 렌더.

---

## 4. web.py 대시보드 서빙 폐기 범위 (task-QY1WXQQI)

session_board가 대시보드 뷰잉을 소유하므로 `agent-kanban-server`의 중복 웹 서빙을 폐기한다.
**대상 레포:** `00.claude-team-mcp/agent-kanban-server/src/agent_kanban/web.py` (FastAPI, 포트 48080).

**폐기 대상:**
- 정적 파일 서빙: `_mount_dashboard()`, `DASHBOARD_DIR`, `StaticFiles` 마운트, `/`→`index.html` `FileResponse`.
- 읽기 REST API: `/api/projects`, `/api/board/{project_id}`, `/api/tasks/{task_id}`, `/api/project-status/{project_id}`
  (이제 session_board Express `/api/kanban/*`가 대체).
- 결과적으로 `web.py`(:48080) 대시보드 서버 전체가 폐기 대상.

**유지:**
- MCP 서버(`server.py`)의 도구 기능은 **그대로 유지**(쓰기·읽기 MCP 도구 정상 동작).
- `db.py`는 유지(MCP 도구와 신규 Express 리더가 참조하는 쿼리 원본·미러 기준).

**제약:**
- **파괴적 변경이므로 실제 삭제 전 사용자 확인 필수**(task-QY1WXQQI 완료조건).
- 관련 문서(README/CLAUDE.md) 갱신.
- 완료조건: MCP 도구 정상 동작 확인 + :48080 서빙 경로 제거(사용자 승인 후).

---

## 5. 화면 목업 (3종 이상)

session_board 셸(상단 고정 헤더 + `data-theme` 토글) 안에 칸반이 어떻게 얹히는지 나타낸 개념 목업.
정확한 픽셀·컴포넌트는 이식(task-VOOp_2aq)·통합(task-46apWJUG)에서 확정.

### 목업 A — 칸반 보드 메인 (`/kanban`, MCP 도달 시)
```
┌──────────────────────────────────────────────────────────────────────────┐
│ Claude Session Dashboard    Timeline  Analytics  Reports  Monitor  [칸반] │← 칸반 탭 조건부 노출
│                                                        🌓 theme   A± zoom  │  (available=true일 때만)
├───────────────────────────────────────────────────┬──────────────────────┤
│  프로젝트: AI-Board 통합 ▼  🔍 검색  우선순위▼ 담당자▼│  프로젝트 상태         │
│                                                     │  ┌──────────────────┐ │
│  Backlog(9) │ Todo(0) │ InProg(1) │ Review(0) │ …  │  │ 진행중 1 · 블로커0│ │
│  ┌─────────┐│         │ ┌────────┐│           │    │  └──────────────────┘ │
│  │Critical │││        │ │High    ││           │    │  에이전트 워크로드     │
│  │DB 리더  │││        │ │라우트  ││           │    │  PM        ▓░░ 1/3    │
│  │@백엔드  │││        │ │@백엔드 ││           │    │  백엔드    ▓▓░ 2/4    │
│  │  v3  💬 │││        │ │ v1     ││           │    │  프론트    ░░░ 0/3    │
│  └─────────┘│         │ └────────┘│           │    │  리뷰어    ░░░ 0/2    │
│  ┌─────────┐│         │           │           │    │                        │
│  │High     │││        │           │           │    │  최근 활동             │
│  │인프라   │││        │           │           │    │  · 백엔드 InProgress   │
│  └─────────┘│         │           │           │    │  · PM Review→Reject    │
│  … 더보기   │         │           │           │    │  · PM 스펙 작성        │
└─────────────┴─────────┴───────────┴───────────┴────┴──────────────────────┘
    ▲ 컬럼별 카드(우선순위색·담당자·버전·최근노트💬), Done/Rejected 기본 접힘
```

### 목업 B — 태스크 상세 다이얼로그 (카드 클릭)
```
        ┌──────────────────────────────────────────────────┐
        │  DB 리더 서비스 (Postgres+SQLite 듀얼)        ✕ │
        │  [Critical]  [InProgress]  담당: 백엔드 개발      │
        ├──────────────────────────────────────────────────┤
        │  설명                                            │
        │  session_board Express에 칸반 DB를 읽기 전용…    │
        │  완료조건: available() 헬퍼 제공, PG/SQLite …    │
        ├──────────────────────────────────────────────────┤
        │  노트 타임라인 (오래된→최신)                     │
        │  ┌──────────────────────────────────────────────┐│
        │  │ system  Task created / Assigned               ││
        │  │ progress 착수 계획: …                          ││
        │  │ handoff  완료한 것 / 검증 / 변경파일           ││ ← note_type 배지 색상
        │  │ review   PASS/FAIL 사유                         ││   (progress/handoff/review/blocker)
        │  └──────────────────────────────────────────────┘│
        └──────────────────────────────────────────────────┘
    ▲ 모달은 .kanban-scope 하위 — 배경(기존 화면)에 스타일 영향 없음
```

### 목업 C — MCP/DB 미도달 시 (칸반 탭 미노출)
```
┌──────────────────────────────────────────────────────────────────────────┐
│ Claude Session Dashboard    Timeline  Analytics  Reports  Monitor         │← '칸반' 탭 없음
│                                                        🌓 theme   A± zoom  │  (available=false → 미생성)
├──────────────────────────────────────────────────────────────────────────┤
│  (기존 4개 탭만 정상 동작 — 레이아웃·스타일 기존 그대로, 칸반 흔적 0)       │
└──────────────────────────────────────────────────────────────────────────┘
    · /api/kanban/available = false (Supabase env 없음 + 로컬 kanban.db 없음)
    · 또는 available 조회 실패(fail-closed) → 동일하게 숨김
    · /kanban 직접 진입해도 라우트 미등록 → 기존 리다이렉트/404
```

### 목업 D — 프로젝트 상태 사이드바 (상세, 보조)
```
┌──────────────────────┐
│ 프로젝트 상태         │
│ 요약  Backlog9 Todo0  │
│       InProg1 Review0 │
│       Done0 Reject0   │
│ ─────────────────────│
│ 블로커 (0)  없음      │  ← 있으면 태스크·사유·담당자 리스트
│ ─────────────────────│
│ 최근 활동 (24h)       │
│ 09:33 PM  Review→Rej  │
│ 00:15 PM  Todo→InProg │
└──────────────────────┘
```

> 목업은 개념 검증용이다. 색·간격·컴포넌트 최종 형태는 §3 테마 병합 규칙을 지키며
> 이식(task-VOOp_2aq)에서 확정하고, task-O1aUOIlJ에서 기존 탭 무회귀와 함께 검증한다.

## 6. 태스크 의존 순서 (참고)

명시적 `선행:` 레이블은 없으나 논리적 순서는 다음과 같다. `/plan-run`은 이 순서로 진행한다.

```
task-Nu4jNhME (스펙·이 문서) [Critical]
├─ 백엔드 트랙
│   task-Lld_mySw (Express DB 리더) [Critical]
│     └─ task-JJxVEf_Q (라우트 5종) [High]
├─ 프론트 트랙
│   task-cJTeQp2t (TS/shadcn 인프라) [High]
│     └─ task-VOOp_2aq (컴포넌트 이식) [High]
│           └─ task-46apWJUG (KanbanPage+탭, JJxVEf_Q도 선행) [High]
├─ task-QY1WXQQI (web.py 폐기) [Medium] — 통합 완료 후, 사용자 승인
└─ 검증/리뷰
    task-O1aUOIlJ (통합 검증) [Medium], task-w51waGcE (코드 리뷰) [Medium]
```

## 7. 승인 체크리스트

- [ ] `/api/kanban/*` 5종 계약과 db.py 미러링 범위 동의
- [ ] DB 도달 감지 규칙(KANBAN_DB_HOST / 로컬 kanban.db) 및 조건부 탭 노출 동의
- [ ] **MCP/DB 미도달 시 칸반 메뉴 미노출**(3중 게이트·fail-closed, §2.2) 동의
- [ ] 테마 병합 전략(shadcn 토큰 → session_board 변수 참조, 서브트리 스코프) 동의
- [ ] **기존 UI 비침범 가드레일**(전역 토큰·기존 변수·기존 컴포넌트 미변경, §3.1) 동의
- [ ] **화면 목업 3종+**(A 보드·B 태스크상세·C 미노출·D 사이드바, §5) 방향 동의
- [ ] web.py(:48080) 정적 서빙 + 읽기 API 폐기, MCP server.py 유지 동의
