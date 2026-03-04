import type { TeamStatus } from '@/types/kanban';
import { ALL_STATUSES, STATUS_CONFIG } from '@/types/kanban';
import { STATUS_ICON_CONFIG } from '@/constants/ui';
import { Progress } from '@/components/ui/progress';

interface Props {
  teamStatus: TeamStatus;
}

export default function StatusSummary({ teamStatus }: Props) {
  const total = Object.values(teamStatus.summary).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-2">
      {ALL_STATUSES.map((status) => {
        const count = teamStatus.summary[status];
        const pct = total > 0 ? (count / total) * 100 : 0;
        const { icon: Icon, color } = STATUS_ICON_CONFIG[status];
        const dimmed = count === 0;

        return (
          <div key={status} className={`flex items-center gap-2 ${dimmed ? 'opacity-40' : ''}`}>
            <Icon size={14} className={color} />
            <span className="text-xs text-muted-foreground w-16 truncate">
              {STATUS_CONFIG[status].label}
            </span>
            <Progress value={pct} className="flex-1 h-2" />
            <span className="text-xs font-medium text-foreground w-5 text-right">{count}</span>
          </div>
        );
      })}
    </div>
  );
}
