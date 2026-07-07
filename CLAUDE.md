# AI-Board

## 원칙
- `.claude/docs/kanban.md` 파일이 있는 경우에는 모든 대화 실행 시 반드시 참조할 것

## 검증 명령 (관찰 가능한 규칙)
- 서버 테스트: `cd agent-kanban-server && uv run pytest tests/ -v`
- 대시보드(칸반 뷰잉): session_board(Claude Session Dashboard)로 이전됨 — 해당 레포에서 `npm run build`로 검증

## 금지사항
- `kanban.db` 및 마이그레이션 스크립트는 명시 요청 없이 수정 금지
- 완료조건에 없는 모호함은 추론으로 채우지 말고 사용자에게 질문할 것

## 계층
- 프로젝트(레포당 1개 = DB의 projects 테이블, 싱글턴) → 플랜(의도 단위) → 태스크(리뷰 체크포인트) → 노트(저널)
- 플랜에 속하지 않은 태스크는 `plan_id=NULL` = 미분류 버킷

## 워크플로우
- 기획: `/plan <요구사항>` — 인터뷰 → 플랜 등록 → 완료조건 포함 태스크 분해 → 승인 → 보드 등록
- 실행: `/clear` 후 새 세션에서 `/plan-run` — 플랜의 태스크를 구현 → 자체 QA → 리뷰 → Done 자율 순환
- 복원: `/resume` — 최신 handoff 노트 기준 컨텍스트 복원
- 회고: `/retro` — 보드 데이터로 리뷰 실효성·프로세스 마찰·우회 측정
