import type { Priority, NoteType } from '../types/kanban';
import {
  AlertCircle,
  ArrowUp,
  Minus,
  ArrowDown,
} from 'lucide-react';

/** Priority icon components — shared across TaskCard, TaskDetailModal */
export const PRIORITY_ICONS: Record<Priority, typeof AlertCircle> = {
  Critical: AlertCircle,
  High: ArrowUp,
  Medium: Minus,
  Low: ArrowDown,
};

/** Note type → Tailwind style classes */
export const NOTE_TYPE_STYLES: Record<NoteType, string> = {
  system: 'bg-gray-100 text-gray-600',
  progress: 'bg-blue-50 text-blue-700',
  blocker: 'bg-red-50 text-red-700',
  handoff: 'bg-yellow-50 text-yellow-700',
  review: 'bg-purple-50 text-purple-700',
};

/** Note type display labels */
export const NOTE_TYPE_LABELS: Record<NoteType, string> = {
  system: 'System',
  progress: 'Progress',
  blocker: 'Blocker',
  handoff: 'Handoff',
  review: 'Review',
};
