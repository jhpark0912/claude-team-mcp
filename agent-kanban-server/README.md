# Agent Kanban MCP Server

Claude Agent Teams 협업을 위한 칸반보드 MCP 서버.

## Quick Start

```bash
# 의존성 설치
uv sync

# 서버 실행
uv run python -m agent_kanban.server

# 테스트
uv run pytest tests/ -v
```

## Claude Code MCP 설정

```json
{
  "mcpServers": {
    "agent-kanban": {
      "command": "uv",
      "args": ["run", "--directory", "D:\\00.claude\\01.mcp\\agent-kanban-server", "python", "-m", "agent_kanban.server"]
    }
  }
}
```

## 기능

### Tools (10개)
| Category | Tool | Description |
|----------|------|-------------|
| Config | `create_team` | 팀 생성 |
| Config | `add_agent` | 에이전트 추가 |
| Lifecycle | `create_task` | 칸반 카드 생성 |
| Lifecycle | `update_task_status` | 상태 변경 (전이 검증 + Optimistic Locking) |
| Lifecycle | `assign_task` | 작업 할당 |
| Collab | `add_note` | 메모 추가 |
| Collab | `flag_blocker` | 블로커 설정/해제 |
| Query | `get_board` | 보드 조회 |
| Query | `get_task_detail` | 카드 상세 |
| Query | `get_team_status` | 팀 통계 |

### Resources (3개)
- `kanban://rules` - 칸반 규칙
- `kanban://board/{team_id}` - 보드 스냅샷
- `kanban://board/{team_id}/agents` - 에이전트 목록

### Prompts (5개)
- `kanban_system_prompt` - 초기화
- `daily_standup_prompt` - 스탠드업
- `task_handoff_prompt` - 인계
- `blocker_escalation_prompt` - 블로커 에스컬레이션
- `task_completion_prompt` - 완료 처리

## 상태 전이
```
Backlog → Todo → InProgress → Review → Done
                    ↑            │
                    └── Rejected ┘
```
