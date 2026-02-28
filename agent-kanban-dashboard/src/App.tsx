import { useState, useMemo } from 'react';
import { PanelRightOpen, PanelRightClose } from 'lucide-react';
import { useTeams, useBoard, useTeamStatus } from './hooks/useKanban';
import TeamSelector from './components/TeamSelector';
import FilterBar from './components/FilterBar';
import KanbanBoard from './components/KanbanBoard';
import SidePanel from './components/SidePanel';
import TaskDetailModal from './components/TaskDetailModal';
import type { FilterState, BoardData, Status } from './types/kanban';
import { ALL_STATUSES } from './types/kanban';
import './App.css';

function App() {
  const { teams, loading: teamsLoading } = useTeams();
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [sidePanelOpen, setSidePanelOpen] = useState(true);
  const [showEmptyColumns, setShowEmptyColumns] = useState(true);
  const [filterState, setFilterState] = useState<FilterState>({
    priority: null,
    assignee: null,
    blockedOnly: false,
    search: '',
  });

  const activeTeamId = selectedTeamId || (teams.length > 0 ? teams[0].id : null);
  const { board, loading: boardLoading, refresh } = useBoard(activeTeamId);
  const { status: teamStatus } = useTeamStatus(activeTeamId);

  // Extract unique assignees from board data
  const assignees = useMemo(() => {
    if (!board) return [];
    const set = new Set<string>();
    for (const status of ALL_STATUSES) {
      for (const task of board.board[status] ?? []) {
        if (task.assigned_to) set.add(task.assigned_to);
      }
    }
    return Array.from(set).sort();
  }, [board]);

  // Filter board data client-side
  const filteredBoard = useMemo((): BoardData | null => {
    if (!board) return null;
    const { priority, assignee, blockedOnly, search } = filterState;
    const hasFilter = priority || assignee || blockedOnly || search;
    if (!hasFilter) return board;

    const searchLower = search.toLowerCase();
    const newBoard = {} as Record<Status, BoardData['board'][Status]>;
    const newCounts = {} as Record<Status, number>;

    for (const status of ALL_STATUSES) {
      const tasks = (board.board[status] ?? []).filter((task) => {
        if (priority && task.priority !== priority) return false;
        if (assignee && task.assigned_to !== assignee) return false;
        if (blockedOnly && !task.is_blocked) return false;
        if (search && !task.title.toLowerCase().includes(searchLower)) return false;
        return true;
      });
      newBoard[status] = tasks;
      newCounts[status] = tasks.length;
    }

    return { ...board, board: newBoard, counts: newCounts };
  }, [board, filterState]);

  if (teamsLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg text-gray-500">Loading...</div>
      </div>
    );
  }

  if (teams.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-lg text-gray-500">No teams found. Create a team via MCP first.</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold text-gray-800">Kanban Dashboard</h1>
          <TeamSelector
            teams={teams}
            selectedId={activeTeamId}
            onChange={setSelectedTeamId}
          />
        </div>
        <div className="flex items-center gap-3">
          {board && (
            <span className="text-xs text-gray-400">
              Updated: {new Date(board.updated_at).toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={refresh}
            className="px-3 py-1.5 text-sm bg-blue-50 text-blue-600 rounded-md hover:bg-blue-100 transition-colors cursor-pointer"
          >
            Refresh
          </button>
          <button
            onClick={() => setSidePanelOpen(!sidePanelOpen)}
            className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-md transition-colors cursor-pointer"
            title={sidePanelOpen ? 'Close side panel' : 'Open side panel'}
          >
            {sidePanelOpen ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
          </button>
        </div>
      </header>

      {/* Filter Bar */}
      {board && (
        <FilterBar
          filterState={filterState}
          onFilterChange={setFilterState}
          assignees={assignees}
          showEmptyColumns={showEmptyColumns}
          onToggleEmptyColumns={() => setShowEmptyColumns((v) => !v)}
        />
      )}

      {/* Main Content */}
      <div className="flex flex-1 min-h-0">
        {/* Board */}
        <main className="flex-1 p-4 overflow-auto">
          {boardLoading ? (
            <div className="flex items-center justify-center h-64 text-gray-400">Loading board...</div>
          ) : filteredBoard ? (
            <KanbanBoard board={filteredBoard} onTaskClick={setSelectedTaskId} showEmptyColumns={showEmptyColumns} />
          ) : null}
        </main>

        {/* Side Panel */}
        {sidePanelOpen && (
          <aside className="w-80 border-l border-gray-200 bg-white p-4 overflow-y-auto shrink-0 transition-all">
            <SidePanel teamStatus={teamStatus} />
          </aside>
        )}
      </div>

      {/* Task Detail Modal */}
      {selectedTaskId && (
        <TaskDetailModal
          taskId={selectedTaskId}
          onClose={() => setSelectedTaskId(null)}
        />
      )}
    </div>
  );
}

export default App;
