import { Inbox, ChevronsUpDown } from 'lucide-react';
import type { Status, TaskCard as TaskCardType } from '@/types/kanban';
import { STATUS_CONFIG } from '@/types/kanban';
import { STATUS_ICON_CONFIG } from '@/constants/ui';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import TaskCard from '@/components/board/TaskCard';

interface Props {
  status: Status;
  tasks: TaskCardType[];
  count: number;
  wipInfo?: string;
  onTaskClick: (taskId: string) => void;
  collapsed: boolean;
  visibleCount: number;
  onToggleCollapse: () => void;
  onShowMore: () => void;
}

export default function BoardColumn({
  status,
  tasks,
  count,
  onTaskClick,
  collapsed,
  visibleCount,
  onToggleCollapse,
  onShowMore,
}: Props) {
  const config = STATUS_CONFIG[status];
  const { icon: StatusIcon, color: iconColor } = STATUS_ICON_CONFIG[status];
  const visibleTasks = tasks.slice(0, visibleCount);
  const remaining = tasks.length - visibleCount;

  return (
    <div className="min-w-[280px] w-[280px] flex-shrink-0 flex flex-col">
      <Collapsible open={!collapsed} onOpenChange={() => onToggleCollapse()}>
        {/* Header */}
        <CollapsibleTrigger asChild>
          <button className="w-full flex items-center gap-2 px-3 py-2.5 rounded-t-lg bg-card border border-border cursor-pointer hover:bg-accent transition-colors">
            <StatusIcon size={16} className={iconColor} />
            <span className="text-sm font-medium text-foreground">{config.label}</span>
            <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-5 ml-auto">
              {count}
            </Badge>
            <ChevronsUpDown size={14} className="text-muted-foreground" />
          </button>
        </CollapsibleTrigger>

        {/* Content */}
        <CollapsibleContent>
          <div className="border border-t-0 border-border rounded-b-lg bg-card/50">
            <ScrollArea className="max-h-[calc(100vh-160px)]">
              <div className="p-2 space-y-1.5">
                {visibleTasks.length === 0 ? (
                  <div className="flex flex-col items-center text-muted-foreground py-6 gap-1.5">
                    <Inbox size={18} />
                    <span className="text-xs">태스크 없음</span>
                  </div>
                ) : (
                  <>
                    {visibleTasks.map((task) => (
                      <TaskCard key={task.id} task={task} onClick={() => onTaskClick(task.id)} />
                    ))}
                    {remaining > 0 && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="w-full h-7 text-xs text-muted-foreground"
                        onClick={(e) => {
                          e.stopPropagation();
                          onShowMore();
                        }}
                      >
                        {remaining}개 더 보기
                      </Button>
                    )}
                  </>
                )}
              </div>
            </ScrollArea>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}
