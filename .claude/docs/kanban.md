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

## 프로젝트 정보 (AI-Board 통합 — session_board)
- 프로젝트 ID : `team-Aa3xGjTv`