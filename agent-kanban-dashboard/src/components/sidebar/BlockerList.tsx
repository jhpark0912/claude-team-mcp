import { AlertTriangle } from 'lucide-react';
import type { Blocker } from '@/types/kanban';

interface Props {
  blockers: Blocker[];
}

export default function BlockerList({ blockers }: Props) {
  if (blockers.length === 0) {
    return <p className="text-xs text-muted-foreground">블로커 없음</p>;
  }

  return (
    <div className="space-y-1.5">
      {blockers.map((b) => (
        <div
          key={b.task_id}
          className="rounded-md border border-red-500/20 bg-red-500/10 px-3 py-2"
        >
          <div className="flex items-start gap-1.5">
            <AlertTriangle size={12} className="text-red-400 mt-0.5 flex-shrink-0" />
            <div className="min-w-0">
              <p className="text-xs font-medium text-red-400 truncate">{b.title}</p>
              <p className="text-[11px] text-red-400/70 mt-0.5">{b.reason}</p>
              {b.assigned_to && (
                <span className="text-[10px] text-red-400/50">{b.assigned_to}</span>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
