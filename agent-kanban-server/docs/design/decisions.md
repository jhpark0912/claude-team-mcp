# Architecture Decision Records (ADR)

## ADR-001: Server-side Transition Validation
**Decision**: 상태 전이 규칙을 서버에서 검증한다.
**Reason**: 프롬프트만으로 제어하면 에이전트가 무시할 수 있다. 위반 시 허용된 전이 목록과 함께 에러 반환.

## ADR-002: Server-generated IDs (nanoid)
**Decision**: Task/Agent/Team ID는 서버(nanoid)가 생성한다.
**Reason**: 멀티에이전트 환경에서 유일성을 보장하기 위해.

## ADR-003: No Column/Board Table
**Decision**: Column/Board 테이블을 제거하고 status Enum으로 관리한다.
**Reason**: 상태가 고정된 상황에서 불필요한 간접 레이어. WIP 제한은 teams.config JSON에 저장. 추후 커스텀 워크플로우 필요 시 마이그레이션.

## ADR-004: Auto System Notes
**Decision**: 상태 변경 시 자동으로 system note를 생성한다.
**Reason**: 에이전트가 add_note를 깜빡해도 최소한의 이력이 보장된다.

## ADR-005: Cross-team Access Validation
**Decision**: agent_id가 task의 team에 소속인지 서버에서 검증한다.
**Reason**: 멀티팀 환경에서 데이터 무결성을 보장.

## ADR-006: Blocker Reason Server Validation
**Decision**: is_blocked=true 시 reason이 없으면 서버에서 에러를 반환한다.
**Reason**: JSON Schema만으로는 조건부 필수를 표현할 수 없으므로 서버 로직에서 검증.
