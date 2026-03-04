import { ClipboardList } from 'lucide-react';
import type { BoardData } from '@/types/kanban';
import { ALL_STATUSES } from '@/types/kanban';
import { useColumnState } from '@/hooks/useColumnState';
import BoardColumn from '@/components/board/BoardColumn';

interface Props {
  board: BoardData;
  onTaskClick: (taskId: string) => void;
}

export default function KanbanBoard({ board, onTaskClick }: Props) {
  const { isCollapsed, getVisibleCount, toggleCollapse, showMore } = useColumnState();

  const totalTasks = ALL_STATUSES.reduce((sum, s) => sum + (board.counts[s] || 0), 0);

  if (totalTasks === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <ClipboardList size={48} className="mb-3" />
        <p className="text-lg font-semibold">태스크가 없습니다</p>
        <p className="text-sm mt-1">MCP를 통해 태스크를 생성하세요</p>
      </div>
    );
  }

  return (
    <div
      className="flex gap-3 p-4 overflow-x-auto overflow-y-hidden items-start h-full"
      onWheel={(e) => {
        if (e.shiftKey) {
          e.currentTarget.scrollLeft += e.deltaY;
        }
      }}
    >
      {ALL_STATUSES.map((status) => (
        <BoardColumn
          key={status}
          status={status}
          tasks={board.board[status] ?? []}
          count={board.counts[status] ?? 0}
          wipInfo={board.wip_status[status]}
          onTaskClick={onTaskClick}
          collapsed={isCollapsed(status)}
          visibleCount={getVisibleCount(status)}
          onToggleCollapse={() => toggleCollapse(status)}
          onShowMore={() => showMore(status)}
        />
      ))}
    </div>
  );
}
