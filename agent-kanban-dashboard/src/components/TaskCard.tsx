import { Ban, User } from 'lucide-react';
import type { TaskCard as TaskCardType } from '../types/kanban';
import { PRIORITY_CONFIG } from '../types/kanban';
import { PRIORITY_ICONS } from '../constants/ui';

interface Props {
  task: TaskCardType;
  onClick: () => void;
}

export default function TaskCard({ task, onClick }: Props) {
  const priority = PRIORITY_CONFIG[task.priority];

  return (
    <div
      onClick={onClick}
      className={`bg-white rounded-md p-2.5 shadow-sm cursor-pointer hover:-translate-y-0.5 hover:shadow-lg transition-all border ${
        task.is_blocked ? 'border-red-400 ring-1 ring-red-200' : 'border-gray-200'
      }`}
    >
      {/* Header: Priority + Blocked */}
      <div className="flex items-center justify-between mb-1.5">
        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${priority.bg} ${priority.color} inline-flex items-center gap-0.5`}>
          {(() => { const Icon = PRIORITY_ICONS[task.priority]; return Icon ? <Icon size={10} /> : null; })()}
          {task.priority}
        </span>
        {task.is_blocked && (
          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-red-100 text-red-700 inline-flex items-center gap-0.5">
            <Ban size={10} />
            BLOCKED
          </span>
        )}
      </div>

      {/* Title */}
      <p className="text-sm font-medium text-gray-800 leading-tight mb-1.5 line-clamp-2">
        {task.title}
      </p>

      {/* Footer: Assignee */}
      <div className="flex items-center">
        {task.assigned_to ? (
          <span className="text-[11px] text-gray-500 truncate max-w-[160px] inline-flex items-center gap-0.5">
            <User size={10} className="flex-shrink-0" />
            {task.assigned_to}
          </span>
        ) : (
          <span className="text-[11px] text-gray-300 italic">Unassigned</span>
        )}
      </div>
    </div>
  );
}
