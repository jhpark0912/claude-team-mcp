# Multi-Agent Collaboration Scenario

## Scenario: Payment Refactoring

### Setup
```
create_team("Payment Refactoring Team") → team-pay01
add_agent(team-pay01, "Alice", "PM")     → agent-alice01
add_agent(team-pay01, "Bob", "Developer")→ agent-bob01
add_agent(team-pay01, "Charlie", "Reviewer") → agent-charlie01
```

### Flow

#### 1. PM Creates Tasks
```
Alice: create_task(team-pay01, "결제 API 에러 핸들링 개선", priority="High", assignee_id=agent-bob01)
Alice: create_task(team-pay01, "단위 테스트 추가", priority="Medium", assignee_id=agent-charlie01)
```

#### 2. Developer Starts Work
```
Bob: update_task_status(task-m1n2o3, "Todo", v=1, comment="분석 시작")
Bob: update_task_status(task-m1n2o3, "InProgress", v=2, comment="코딩 시작")
Bob: add_note(task-m1n2o3, agent-bob01, "PaymentService 3개 catch 블록 전환 완료")
```

#### 3. Blocker Encountered
```
Bob: flag_blocker(task-x1y2, is_blocked=true, reason="외부 API 키 발급 대기", v=2)
```

#### 4. Handoff to Reviewer
```
Bob: update_task_status(task-m1n2o3, "Review", v=5)
Bob: assign_task(task-m1n2o3, agent-charlie01, v=6)
Bob: add_note(task-m1n2o3, agent-bob01, "리뷰 요청: ...", note_type="handoff")
```

#### 5. Version Conflict Resolution
```
Charlie: update_task_status(task-m1n2o3, "Done", v=7)
  → VERSION_CONFLICT (Bob already updated to v=8)
Charlie: get_task_detail(task-m1n2o3)  → current v=8
Charlie: update_task_status(task-m1n2o3, "Done", v=8)  → Success
```

#### 6. Daily Standup
```
PM: get_team_status(team-pay01)
PM: get_board(team-pay01)
→ Summary report with agent workloads, blockers, progress
```
