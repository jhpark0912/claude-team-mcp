import { useState, useMemo, useCallback } from 'react';
import { useTeams, useBoard, useTeamStatus } from '@/hooks/useKanban';
import { SidebarProvider, SidebarInset } from '@/components/ui/sidebar';
import { TooltipProvider } from '@/components/ui/tooltip';
import AppSidebar from '@/components/layout/AppSidebar';
import BoardToolbar from '@/components/layout/BoardToolbar';
import KanbanBoard from '@/components/board/KanbanBoard';
import TaskDetailDialog from '@/components/board/TaskDetailDialog';
import type { FilterState, BoardData, Status } from '@/types/kanban';
import { ALL_STATUSES } from '@/types/kanban';

function App() {
  const { teams, loading: teamsLoading } = useTeams();
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [filterState, setFilterState] = useState<FilterState>({
    priority: null, assignee: null, blockedOnly: false, search: '',
  });

  const activeTeamId = selectedTeamId || (teams.length > 0 ? teams[0].id : null);
  const { board, loading: boardLoading, refresh } = useBoard(activeTeamId);
  const { status: teamStatus } = useTeamStatus(activeTeamId);

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

  // 사이드바 에이전트 클릭 → 담당자 필터 토글
  const handleAgentClick = useCallback((agentName: string) => {
    // 보드의 assigned_to는 "이름 (역할)" 형태 — 에이전트 이름으로 매칭되는 assignee 찾기
    const matched = assignees.find((a) => a.startsWith(agentName));
    const target = matched ?? agentName;

    setFilterState((prev) => ({
      ...prev,
      assignee: prev.assignee === target ? null : target,
    }));
  }, [assignees]);

  const filteredBoard = useMemo((): BoardData | null => {
    if (!board) return null;
    const { priority, assignee, blockedOnly, search } = filterState;
    if (!priority && !assignee && !blockedOnly && !search) return board;

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
      <div className="flex items-center justify-center min-h-screen bg-background">
        <div className="text-lg text-muted-foreground">로딩 중...</div>
      </div>
    );
  }

  if (teams.length === 0) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-background">
        <div className="text-lg text-muted-foreground">팀이 없습니다. MCP를 통해 팀을 먼저 생성하세요.</div>
      </div>
    );
  }

  return (
    <TooltipProvider>
      <SidebarProvider className="h-svh !min-h-0">
        <AppSidebar
          teams={teams}
          selectedTeamId={activeTeamId}
          onTeamChange={setSelectedTeamId}
          teamStatus={teamStatus}
          onRefresh={refresh}
          updatedAt={board?.updated_at ?? null}
          selectedAssignee={filterState.assignee}
          onAgentClick={handleAgentClick}
        />
        <SidebarInset className="h-svh !min-h-0 overflow-hidden">
          {board && (
            <BoardToolbar
              filterState={filterState}
              onFilterChange={setFilterState}
              assignees={assignees}
            />
          )}
          <div className="flex-1 min-h-0">
            {boardLoading ? (
              <div className="flex items-center justify-center h-64 text-muted-foreground">보드 로딩 중...</div>
            ) : filteredBoard ? (
              <KanbanBoard board={filteredBoard} onTaskClick={setSelectedTaskId} />
            ) : null}
          </div>
        </SidebarInset>
        <TaskDetailDialog taskId={selectedTaskId} onClose={() => setSelectedTaskId(null)} />
      </SidebarProvider>
    </TooltipProvider>
  );
}

export default App;
