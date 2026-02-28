# Data Model

## Entity Relationship
```
Team (1) ──▶ (N) Agent
Team (1) ──▶ (N) Task ──▶ (N) Note
Task ──▶ Agent (assignee)
```

## DB Schema (SQLite)

### teams
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | nanoid (team-xxxxxxxx) |
| name | TEXT NOT NULL | 팀 이름 |
| created_at | TEXT | ISO 8601 |
| config | TEXT | JSON: `{"wip_limits": {"InProgress": 3}}` |

### agents
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | nanoid (agent-xxxxxxxx) |
| team_id | TEXT FK→teams | 소속 팀 |
| name | TEXT NOT NULL | 에이전트 이름 |
| role | TEXT | PM, Developer, Reviewer, Tester, Designer |
| created_at | TEXT | ISO 8601 |

### tasks
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | nanoid (task-xxxxxxxx) |
| team_id | TEXT FK→teams | 소속 팀 |
| title | TEXT NOT NULL | 작업 제목 |
| description | TEXT | 상세 설명 |
| status | TEXT | Backlog, Todo, InProgress, Review, Done, Rejected |
| priority | TEXT | Low, Medium, High, Critical |
| assignee_id | TEXT FK→agents | 담당자 |
| is_blocked | INTEGER | 0 or 1 |
| blocker_reason | TEXT | 블로커 사유 |
| version | INTEGER | Optimistic Locking용 |
| created_at | TEXT | ISO 8601 |
| updated_at | TEXT | ISO 8601 |

### notes
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT PK | nanoid (note-xxxxxxxx) |
| task_id | TEXT FK→tasks | ON DELETE CASCADE |
| agent_id | TEXT | 작성자 (또는 "system") |
| content | TEXT NOT NULL | 메모 내용 |
| note_type | TEXT | progress, blocker, handoff, review, system |
| created_at | TEXT | ISO 8601 |

## State Machine

### Valid Transitions
```
Backlog → Todo → InProgress → Review → Done
                    ↑            │
                    └── Rejected ┘
Todo → Backlog (우선순위 재조정)
```

### Auto System Notes
상태 변경, 할당, 블로커 변경 시 자동 `note_type='system'` 노트 생성.
