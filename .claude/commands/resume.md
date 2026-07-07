칸반보드에서 내 현재 상태를 복원해줘.

1. `.claude/docs/kanban.md`에서 Team ID와 Agent ID를 확인
2. `get_board`로 보드 전체 조회
3. 내 에이전트에 할당된 InProgress 작업 파악
4. 해당 작업의 `get_task_detail`에서 **최신 handoff 노트를 최우선으로** 읽는다
   - handoff 노트 스키마: 완료한 것 / 검증 명령과 결과 / 검증 못한 것 / 주의사항 / 변경 파일
   - handoff 노트가 없으면 최근 progress 노트로 대체
5. 복원 요약 제시: 태스크의 완료조건 / 완료한 것 / 남은 것 / 주의사항
6. 실행을 이어가려면 /team-run 안내
