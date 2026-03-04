import { Ban } from 'lucide-react';
import type { TaskCard as TaskCardType } from '@/types/kanban';
import { PRIORITY_CONFIG } from '@/types/kanban';
import { PRIORITY_ICONS } from '@/constants/ui';
import { Badge } from '@/components/ui/badge';

interface Props {
  task: TaskCardType;
  onClick: () => void;
}

export default function TaskCard({ task, onClick }: Props) {
  const priority = PRIORITY_CONFIG[task.priority];
  const PriorityIcon = PRIORITY_ICONS[task.priority];

  return (
    <div
      onClick={onClick}
      className={`rounded-md px-3 py-2 cursor-pointer hover:bg-accent transition-colors border ${
        task.is_blocked
          ? 'border-red-500/30 bg-red-500/5'
          : 'border-transparent bg-card'
      }`}
    >
      {/* Top row: priority + blocked + assignee */}
      <div className="flex items-center gap-1.5 mb-1">
        <span className={`inline-flex items-center gap-0.5 ${priority.color}`}>
          <PriorityIcon size={12} />
        </span>
        <span className={`text-[10px] font-medium ${priority.color}`}>
          {task.priority}
        </span>
        {task.is_blocked && (
          <Badge variant="destructive" className="text-[9px] px-1 py-0 h-4 gap-0.5">
            <Ban size={8} />
            BLOCKED
          </Badge>
        )}
        {task.assigned_to && (
          <span className="text-[10px] text-muted-foreground truncate ml-auto max-w-[100px]">
            {task.assigned_to}
          </span>
        )}
      </div>

      {/* Title */}
      <p className="text-sm font-medium text-foreground leading-tight line-clamp-1">
        {task.title}
      </p>
    </div>
  );
}
