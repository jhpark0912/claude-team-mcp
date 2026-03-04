import type { Priority, Status, NoteType } from '../types/kanban';
import {
  AlertCircle,
  ArrowUp,
  Minus,
  ArrowDown,
  Circle,
  CircleDot,
  Timer,
  Eye,
  CircleCheck,
  CircleX,
} from 'lucide-react';

/** Priority icon components */
export const PRIORITY_ICONS: Record<Priority, typeof AlertCircle> = {
  Critical: AlertCircle,
  High: ArrowUp,
  Medium: Minus,
  Low: ArrowDown,
};

/** Status icon + color config (Linear style) */
export const STATUS_ICON_CONFIG: Record<Status, {
  icon: typeof Circle;
  color: string;
}> = {
  Backlog: { icon: Circle, color: 'text-muted-foreground' },
  Todo: { icon: CircleDot, color: 'text-yellow-500' },
  InProgress: { icon: Timer, color: 'text-blue-500' },
  Review: { icon: Eye, color: 'text-purple-500' },
  Done: { icon: CircleCheck, color: 'text-green-500' },
  Rejected: { icon: CircleX, color: 'text-red-500' },
};

/** Note type → dark theme Tailwind style classes */
export const NOTE_TYPE_STYLES: Record<NoteType, string> = {
  system: 'bg-muted text-muted-foreground',
  progress: 'bg-blue-500/15 text-blue-400',
  blocker: 'bg-red-500/15 text-red-400',
  handoff: 'bg-yellow-500/15 text-yellow-400',
  review: 'bg-purple-500/15 text-purple-400',
};

/** Note type display labels */
export const NOTE_TYPE_LABELS: Record<NoteType, string> = {
  system: '시스템',
  progress: '진행',
  blocker: '블로커',
  handoff: '인수인계',
  review: '리뷰',
};
