export interface Team {
  id: string;
  name: string;
  created_at: string;
}

export interface TaskCard {
  id: string;
  title: string;
  priority: Priority;
  assigned_to: string | null;
  is_blocked: boolean;
  version: number;
  latest_note?: string;
}

export interface BoardData {
  team: string;
  counts: Record<Status, number>;
  board: Record<Status, TaskCard[]>;
  wip_status: Record<string, string>;
  updated_at: string;
}

export interface TaskNote {
  id: string;
  agent: string;
  content: string;
  note_type: 'progress' | 'blocker' | 'handoff' | 'review' | 'system';
  created_at: string;
}

export interface TaskDetail {
  id: string;
  title: string;
  description: string;
  status: Status;
  priority: Priority;
  is_blocked: boolean;
  blocker_reason: string | null;
  version: number;
  assigned_to: { id: string; name: string; role: string } | null;
  team: { id: string; name: string };
  notes: TaskNote[];
  created_at: string;
  updated_at: string;
}

export interface AgentWorkload {
  name: string;
  role: string;
  in_progress: number;
  total: number;
}

export interface Blocker {
  task_id: string;
  title: string;
  reason: string;
  assigned_to: string | null;
}

export interface Activity {
  agent: string;
  action: string;
  task: string;
  detail: string;
  at: string;
}

export interface TeamStatus {
  team: string;
  summary: Record<Status, number>;
  agents: AgentWorkload[];
  blockers: Blocker[];
  recent_activity: Activity[];
}

export type Status = 'Backlog' | 'Todo' | 'InProgress' | 'Review' | 'Done' | 'Rejected';
export type Priority = 'Low' | 'Medium' | 'High' | 'Critical';

export const ALL_STATUSES: Status[] = ['Backlog', 'Todo', 'InProgress', 'Review', 'Done', 'Rejected'];

export const PRIORITY_CONFIG: Record<Priority, { color: string; bg: string }> = {
  Critical: { color: 'text-red-400', bg: 'bg-red-500/15' },
  High: { color: 'text-orange-400', bg: 'bg-orange-500/15' },
  Medium: { color: 'text-blue-400', bg: 'bg-blue-500/15' },
  Low: { color: 'text-muted-foreground', bg: 'bg-muted' },
};

export const STATUS_CONFIG: Record<Status, { label: string; color: string; accent: string }> = {
  Backlog: { label: '백로그', color: 'text-muted-foreground', accent: 'bg-muted-foreground' },
  Todo: { label: '할 일', color: 'text-yellow-500', accent: 'bg-yellow-500' },
  InProgress: { label: '진행 중', color: 'text-blue-500', accent: 'bg-blue-500' },
  Review: { label: '리뷰', color: 'text-purple-500', accent: 'bg-purple-500' },
  Done: { label: '완료', color: 'text-green-500', accent: 'bg-green-500' },
  Rejected: { label: '거절', color: 'text-red-500', accent: 'bg-red-500' },
};

export interface FilterState {
  priority: Priority | null;
  assignee: string | null;
  blockedOnly: boolean;
  search: string;
}

export interface DisplayOptions {
  showEmptyColumns: boolean;
}

export type NoteType = 'progress' | 'blocker' | 'handoff' | 'review' | 'system';

/** 컬럼별 기본 카드 표시 개수 */
export const COLUMN_CARD_LIMITS: Record<Status, number> = {
  Backlog: 10,
  Todo: 10,
  InProgress: 20,
  Review: 10,
  Done: 5,
  Rejected: 3,
};

/** 기본 접힌 컬럼 */
export const DEFAULT_COLLAPSED: Status[] = ['Done', 'Rejected'];

/** 더 보기 클릭 시 추가 로드 수 */
export const CARD_LOAD_INCREMENT = 10;
