# MCP Tool Specifications

## Configuration (2)

### 1. create_team
- **Input**: `name` (string, required)
- **Output**: `{id, name, created_at, message}`

### 2. add_agent
- **Input**: `team_id`, `name`, `role` (PM/Developer/Reviewer/Tester/Designer)
- **Output**: `{id, team_id, name, role, created_at, message}`
- **Validation**: team must exist

## Task Lifecycle (3)

### 3. create_task
- **Input**: `team_id`, `title`, `description?`, `priority?`, `assignee_id?`
- **Output**: `{id, title, status, priority, version, assigned_to, created_at, message}`
- **Validation**: team exists, assignee belongs to team
- **Auto Notes**: "Task created by..." + "Assigned to..." (if assignee_id)

### 4. update_task_status
- **Input**: `task_id`, `status`, `expected_version`, `agent_id?`, `comment?`
- **Output**: `{task_id, title, previous_status, new_status, version, updated_at, message}`
- **Validation**: transition rules, WIP limits, optimistic locking
- **Errors**: INVALID_TRANSITION, WIP_LIMIT_EXCEEDED, VERSION_CONFLICT

### 5. assign_task
- **Input**: `task_id`, `assignee_id`, `expected_version`
- **Output**: `{task_id, title, assigned_to, version, message}`
- **Validation**: cross-team check, optimistic locking

## Collaboration (2)

### 6. add_note
- **Input**: `task_id`, `agent_id`, `content`, `note_type?`
- **Output**: `{task_id, note: {id, agent, content, note_type, created_at}, total_notes, message}`
- **Validation**: agent belongs to task's team

### 7. flag_blocker
- **Input**: `task_id`, `is_blocked`, `expected_version`, `reason?`
- **Output**: `{task_id, title, is_blocked, blocker_reason, version, message}`
- **Validation**: reason required when is_blocked=true

## Board Query (3)

### 8. get_board
- **Input**: `team_id`
- **Output**: board grouped by status with counts, WIP status

### 9. get_task_detail
- **Input**: `task_id`
- **Output**: full task info with all notes

### 10. get_team_status
- **Input**: `team_id`, `activity_hours?` (default 24)
- **Output**: summary counts, agent workloads, blockers, recent activity

## Resources (3)
- `kanban://rules` - Static kanban rules
- `kanban://board/{team_id}` - Board markdown snapshot (subscribable)
- `kanban://board/{team_id}/agents` - Agent list + workload

## Prompts (5)
- `kanban_system_prompt(team_id, agent_id)` - Initial system context
- `daily_standup_prompt(team_id)` - Standup template
- `task_handoff_prompt(task_id, from_agent_id, to_agent_id)` - Handoff guide
- `blocker_escalation_prompt(task_id)` - Blocker escalation guide
- `task_completion_prompt(task_id, agent_id)` - Completion checklist
