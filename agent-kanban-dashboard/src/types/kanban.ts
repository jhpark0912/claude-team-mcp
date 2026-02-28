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
  Critical: { color: 'text-red-700', bg: 'bg-red-100' },
  High: { color: 'text-orange-700', bg: 'bg-orange-100' },
  Medium: { color: 'text-blue-700', bg: 'bg-blue-100' },
  Low: { color: 'text-gray-600', bg: 'bg-gray-100' },
};

export const STATUS_CONFIG: Record<Status, { label: string; color: string; accent: string }> = {
  Backlog: { label: 'Backlog', color: 'bg-gray-200', accent: 'bg-gray-400' },
  Todo: { label: 'Todo', color: 'bg-yellow-200', accent: 'bg-yellow-400' },
  InProgress: { label: 'In Progress', color: 'bg-blue-200', accent: 'bg-blue-500' },
  Review: { label: 'Review', color: 'bg-purple-200', accent: 'bg-purple-500' },
  Done: { label: 'Done', color: 'bg-green-200', accent: 'bg-green-500' },
  Rejected: { label: 'Rejected', color: 'bg-red-200', accent: 'bg-red-400' },
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
