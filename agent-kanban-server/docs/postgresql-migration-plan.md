# PostgreSQL 마이그레이션 계획서

> 작성일: 2026-03-10
> 상태: 계획 수립
> 이전 계획: `mysql-migration-plan.md` (MySQL → PostgreSQL로 변경, 해당 파일 폐기)

---

## 1. 배경 및 목적

### 현재 구조
- **MCP 서버**: 로컬 stdio (Claude Desktop과 직접 통신)
- **DB**: 로컬 SQLite (`kanban.db`)
- **문제**: 팀 내 에이전트들이 동일 DB를 공유하지 못함 (단일 사용자 환경)

### 전환 목표
- **MCP 서버**: 로컬 stdio 유지 (변경 없음)
- **DB**: 로컬 SQLite → GCP VM PostgreSQL (공유 DB)
- **효과**: 여러 Claude 인스턴스가 동일 칸반 보드를 공유 가능

### 전환 이유
- GCP SSE 방식은 Claude Code의 OAuth 인증 요구사항 때문에 실현 불가
- MCP 서버를 클라우드에 올리는 대신 DB만 클라우드로 이동
- 로컬 stdio 방식을 유지하면서 데이터 공유 달성
- MySQL 대신 PostgreSQL 선택: 네이티브 BOOLEAN, UTF-8 기본 지원, 추가 설정 불필요

---

## 2. 현재 데이터 현황

| 테이블 | 레코드 수 |
|--------|----------|
| teams  | 6        |
| agents | 21       |
| tasks  | 189      |
| notes  | 1,101    |

- **원본**: `agent-kanban-server/kanban.db` (WAL 모드, 체크포인트 완료 확인)

---

## 3. 기술 변경 사항

### 3.1 SQLite vs PostgreSQL 주요 차이점

| 항목 | SQLite (현재) | PostgreSQL (목표) |
|------|--------------|------------------|
| 드라이버 | `sqlite3` (표준 라이브러리) | `psycopg2-binary` (추가 설치) |
| 플레이스홀더 | `?` | `%s` |
| 현재 시각 | `datetime('now')` | `NOW()` |
| 시각 연산 | `datetime('now', '-24 hours')` | `NOW() - INTERVAL '24 hours'` |
| 멀티문 실행 | `executescript()` | 개별 `execute()` |
| Row Factory | `sqlite3.Row` (dict-like) | `RealDictCursor` |
| 설정 pragma | `PRAGMA journal_mode=WAL` | 제거 |
| 외래키 | `PRAGMA foreign_keys=ON` | PostgreSQL 기본 지원 |
| BOOLEAN | `INTEGER (0/1)` | `BOOLEAN` (네이티브) |
| TEXT 기본값 | `DEFAULT (datetime('now'))` | `DEFAULT NOW()` |
| 문자셋 설정 | 별도 설정 없음 | 불필요 (기본 UTF-8) |

### 3.2 스키마 변환

**SQLite 현재:**
```sql
created_at TEXT DEFAULT (datetime('now'))
is_blocked INTEGER NOT NULL DEFAULT 0
```

**PostgreSQL 전환:**
```sql
created_at TIMESTAMP DEFAULT NOW()
is_blocked BOOLEAN NOT NULL DEFAULT FALSE
```

### 3.3 쿼리 변환 예시

| SQLite | PostgreSQL |
|--------|-----------|
| `WHERE id=?` | `WHERE id=%s` |
| `datetime('now')` | `NOW()` |
| `datetime('now', '-24 hours')` | `NOW() - INTERVAL '24 hours'` |
| `conn.executescript(SCHEMA)` | 스키마를 `\n\n`으로 split 후 개별 execute |
| `sqlite3.connect(path)` | `psycopg2.connect(host, user, password, dbname, port)` |
| `conn.row_factory = sqlite3.Row` | `cursor = conn.cursor(cursor_factory=RealDictCursor)` |

---

## 4. 인프라 작업 (GCP VM)

> MCP 서버는 로컬에서 실행되므로 GCP VM에는 PostgreSQL만 설치.
> 환경변수는 로컬 PC에 설정. (GCP VM에 env 파일 불필요)

### Step 1. VM 생성 및 정적 IP 할당 (`task-O92eAAhX`)

```
- 머신 유형: e2-micro
- OS: Ubuntu 22.04 LTS
- 리전: asia-northeast3 (서울)
- 정적 외부 IP 할당
```

### Step 2. 방화벽 규칙 설정 (`task-uylX35Iu`)

```
- PostgreSQL 포트 5432: 내 IP 대역 /24 허용 (유동 IP 대응)
- MCP 서버 포트 8000: 불필요 (MCP는 로컬 stdio 유지)
```

### Step 3. VM 환경 셋업 (`task-oZqa0rnq`)

```bash
sudo apt update && sudo apt upgrade -y
curl -LsSf https://astral.sh/uv/install.sh | sh
sudo apt install -y git
git clone <repo-url> ~/ai-board
```

### Step 4. PostgreSQL 설치 및 설정 (`task-y7dfRC8F`)

```bash
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable postgresql

sudo -u postgres psql
```
```sql
CREATE DATABASE ai_board;
CREATE USER ai_board_user WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE ai_board TO ai_board_user;
```
```bash
# 외부 접속 허용
sudo nano /etc/postgresql/16/main/postgresql.conf
  → listen_addresses = '*'

sudo nano /etc/postgresql/16/main/pg_hba.conf
  → host  ai_board  ai_board_user  <내IP대역>/24  md5

sudo systemctl restart postgresql
```

---

## 5. 코드 작업

### Task 1: db.py PostgreSQL 전환 (`task-LCHAL4FH`)
**담당**: Developer - mcp 기능개선
**작업 내용**:
- `psycopg2-binary` 드라이버로 교체
- `get_connection()`: `sqlite3.connect` → `psycopg2.connect`
- 모든 `?` 플레이스홀더 → `%s` 일괄 변환
- `datetime('now')` → `NOW()` 변환
- `datetime('now', '-N hours')` → `NOW() - INTERVAL 'N hours'` 변환
- `executescript()` → 개별 `execute()` 호출로 분리
- `sqlite3.Row` → `RealDictCursor` 로 교체
- `PRAGMA` 구문 제거
- Boolean 처리: PostgreSQL `BOOLEAN` 네이티브 사용

### Task 2: 마이그레이션 스크립트 작성 (`task-uPRjbX3Q`)
**담당**: Developer - mcp 기능개선
**산출물**: `agent-kanban-server/scripts/migrate_sqlite_to_pg.py`
**작업 내용**:
- SQLite `kanban.db` 읽기
- PostgreSQL 스키마 생성 (PostgreSQL 전용 DDL)
- 4개 테이블 순서대로 INSERT: teams → agents → tasks → notes
- 타입 변환: `INTEGER(0/1)` → Python `bool` → PostgreSQL `BOOLEAN`
- 실행 후 레코드 수 검증 출력
- `--dry-run` 옵션 지원

### Task 3: 환경변수 및 설정 정리 (`task-27m8D57l`)
**담당**: Developer - mcp 대시보드 화면
**작업 내용**:
- `.env.example` 업데이트:
  ```
  # PostgreSQL DB 연결 (로컬 PC에 설정)
  KANBAN_DB_HOST=<gcp-vm-ip>
  KANBAN_DB_PORT=5432
  KANBAN_DB_USER=ai_board_user
  KANBAN_DB_PASSWORD=<password>
  KANBAN_DB_NAME=ai_board
  ```
- `db.py`에서 환경변수 읽기 로직 추가
- `pyproject.toml`에 `psycopg2-binary` 의존성 추가
- Claude Desktop `claude_desktop_config.json` 설정 예시 추가

### Task 4: 코드 리뷰 (`task-ucDwLT1I`)
**담당**: Reviewer
**작업 내용**:
- Task 1, 2, 3 완료 후 전체 코드 리뷰
- SQL Injection 취약점 검토
- 연결 풀링 필요 여부 검토
- 에러 처리 완결성 검토

---

## 6. 환경변수 설정 위치

> MCP 서버는 로컬에서 실행되므로 환경변수는 **로컬 PC**에 설정.

**방법 A: Claude Desktop config (`claude_desktop_config.json`)**
```json
{
  "mcpServers": {
    "agent-kanban": {
      "command": "uv",
      "args": ["run", "python", "server.py"],
      "env": {
        "KANBAN_DB_HOST": "<gcp-vm-ip>",
        "KANBAN_DB_PORT": "5432",
        "KANBAN_DB_USER": "ai_board_user",
        "KANBAN_DB_PASSWORD": "your_password",
        "KANBAN_DB_NAME": "ai_board"
      }
    }
  }
}
```

**방법 B: 로컬 `.env` 파일**
```
agent-kanban-server/.env  ← .gitignore에 포함
```

---

## 7. 의존 관계

```
Step 1~4 (GCP 인프라)
    └─→ Task 1 (db.py 전환)             ─┐
    └─→ Task 2 (마이그레이션 스크립트)   ─┼─→ Task 4 (리뷰)
Task 3 (환경변수 정리)  ─────────────────┘
```

---

## 8. 주요 결정 사항

| 결정 | 내용 | 이유 |
|------|------|------|
| DB 드라이버 | psycopg2-binary | 표준 Python PostgreSQL 드라이버, 바이너리 패키지로 빌드 불필요 |
| DB 엔진 | PostgreSQL (MySQL에서 변경) | 네이티브 BOOLEAN, 기본 UTF-8, 추가 문자셋 설정 불필요 |
| 연결 방식 | 단일 연결 (현재 구조 유지) | MCP stdio 특성상 단일 프로세스, 연결 풀 불필요 |
| 환경변수 위치 | 로컬 PC | MCP 서버가 로컬 실행이므로 GCP VM에 env 불필요 |
| IP 허용 방식 | /24 대역 | 사내 유동 IP 대응, Tailscale/VPN 설치 불가 환경 |
| 마이그레이션 방향 | 로컬 SQLite → GCP PostgreSQL | GCP DB는 비어있음, 로컬이 소스 |

---

## 9. 롤백 계획

- SQLite `kanban.db` 파일을 마이그레이션 전에 백업 유지
- `KANBAN_DB_HOST` 미설정 시 SQLite 폴백 동작 구현 권장

---

## 10. 검증 계획

마이그레이션 완료 후 확인 항목:

- [ ] PostgreSQL 레코드 수 = SQLite 레코드 수 (teams: 6, agents: 21, tasks: 189, notes: 1101)
- [ ] `get_board` MCP 도구 정상 응답
- [ ] `create_task` / `update_task_status` 정상 동작
- [ ] `add_note` / `flag_blocker` 정상 동작
- [ ] 옵티미스틱 락킹 (`version` 충돌) 정상 작동
- [ ] `get_team_status` 활동 시간 필터 정상 작동 (`INTERVAL`)
