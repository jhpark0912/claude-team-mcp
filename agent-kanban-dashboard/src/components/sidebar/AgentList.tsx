import type { AgentWorkload } from '@/types/kanban';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

interface Props {
  agents: AgentWorkload[];
  selectedAssignee: string | null;
  onAgentClick: (name: string) => void;
}

export default function AgentList({ agents, selectedAssignee, onAgentClick }: Props) {
  if (agents.length === 0) {
    return <p className="text-xs text-muted-foreground">에이전트 없음</p>;
  }

  return (
    <div className="space-y-1.5">
      {agents.map((agent) => {
        const isSelected = selectedAssignee !== null &&
          agent.name === selectedAssignee.replace(/\s*\(.*\)$/, '');

        return (
          <div
            key={agent.name}
            onClick={() => onAgentClick(agent.name)}
            className={cn(
              'flex items-center justify-between rounded-md px-3 py-2 cursor-pointer transition-colors',
              isSelected
                ? 'bg-primary/15 ring-1 ring-primary/40'
                : 'bg-secondary hover:bg-accent',
            )}
          >
            <div className="flex items-center gap-1.5 min-w-0">
              <span className={cn(
                'text-sm font-medium truncate',
                isSelected ? 'text-primary' : 'text-foreground',
              )}>
                {agent.name}
              </span>
              <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                {agent.role}
              </Badge>
            </div>
            <div className="flex items-center gap-2 text-xs flex-shrink-0">
              {agent.in_progress > 0 && (
                <Badge variant="default" className="text-[10px] px-1.5 py-0">
                  {agent.in_progress} 진행
                </Badge>
              )}
              <span className="text-muted-foreground">{agent.total}건</span>
            </div>
          </div>
        );
      })}
    </div>
  );
}
