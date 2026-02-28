import { Inbox, ClipboardList } from 'lucide-react';
import type { BoardData, Status } from '../types/kanban';
import { ALL_STATUSES, STATUS_CONFIG } from '../types/kanban';
import TaskCard from './TaskCard';

interface Props {
  board: BoardData;
  onTaskClick: (taskId: string) => void;
  showEmptyColumns?: boolean;
}

export default function KanbanBoard({ board, onTaskClick, showEmptyColumns = true }: Props) {
  const totalTasks = ALL_STATUSES.reduce((sum, s) => sum + (board.counts[s] || 0), 0);

  if (totalTasks === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-400">
        <ClipboardList size={48} className="mb-3" />
        <p className="text-lg font-semibold text-gray-500">No tasks yet</p>
        <p className="text-sm mt-1">Create tasks via MCP to get started</p>
      </div>
    );
  }

  const visibleStatuses = showEmptyColumns
    ? ALL_STATUSES
    : ALL_STATUSES.filter((s) => (board.board[s]?.length ?? 0) > 0);

  return (
    <div className="flex gap-3 min-w-max items-start">
      {visibleStatuses.map((status) => (
        <Column
          key={status}
          status={status}
          tasks={board.board[status]}
          count={board.counts[status]}
          wipInfo={board.wip_status[status]}
          onTaskClick={onTaskClick}
        />
      ))}
    </div>
  );
}

function Column({
  status,
  tasks,
  count,
  wipInfo,
  onTaskClick,
}: {
  status: Status;
  tasks: BoardData['board'][Status];
  count: number;
  wipInfo?: string;
  onTaskClick: (taskId: string) => void;
}) {
  const config = STATUS_CONFIG[status];

  return (
    <div className="w-64 flex-shrink-0">
      {/* Accent bar */}
      <div className={`${config.accent} h-1 rounded-t`} />

      {/* Column Header */}
      <div className="bg-white px-3 py-2 flex items-center justify-between border-x border-gray-200">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-sm text-gray-700">{config.label}</span>
          <span className="text-xs font-medium text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">
            {count}
          </span>
        </div>
        {wipInfo && (
          <span className="text-xs text-gray-400">WIP: {wipInfo}</span>
        )}
      </div>

      {/* Cards */}
      <div className="bg-gray-50 rounded-b-lg p-2 space-y-1.5 border border-t-0 border-gray-200">
        {tasks.length === 0 ? (
          <div className="flex flex-col items-center text-gray-400 py-4 gap-1">
            <Inbox size={16} />
            <span className="text-xs">No tasks</span>
          </div>
        ) : (
          tasks.map((task) => (
            <TaskCard key={task.id} task={task} onClick={() => onTaskClick(task.id)} />
          ))
        )}
      </div>
    </div>
  );
}
