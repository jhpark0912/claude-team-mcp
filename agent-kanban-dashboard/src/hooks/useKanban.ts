import { useState, useEffect, useCallback } from 'react';
import type { Team, BoardData, TaskDetail, TeamStatus } from '../types/kanban';

const API_BASE = '/api';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`API Error: ${res.status}`);
  return res.json();
}

export function useTeams() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchJson<Team[]>(`${API_BASE}/teams`)
      .then(setTeams)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return { teams, loading };
}

export function useBoard(teamId: string | null, intervalMs = 15000) {
  const [board, setBoard] = useState<BoardData | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(() => {
    if (!teamId) return;
    fetchJson<BoardData>(`${API_BASE}/board/${teamId}`)
      .then(setBoard)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [teamId]);

  useEffect(() => {
    setLoading(true);
    refresh();
    const timer = setInterval(refresh, intervalMs);
    return () => clearInterval(timer);
  }, [refresh, intervalMs]);

  return { board, loading, refresh };
}

export function useTaskDetail(taskId: string | null, intervalMs = 10000) {
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!taskId) {
      setTask(null);
      return;
    }
    setLoading(true);
    fetchJson<TaskDetail>(`${API_BASE}/tasks/${taskId}`)
      .then(setTask)
      .catch(console.error)
      .finally(() => setLoading(false));

    const timer = setInterval(() => {
      fetchJson<TaskDetail>(`${API_BASE}/tasks/${taskId}`)
        .then(setTask)
        .catch(console.error);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [taskId, intervalMs]);

  return { task, loading };
}

export function useTeamStatus(teamId: string | null, intervalMs = 15000) {
  const [status, setStatus] = useState<TeamStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!teamId) return;
    setLoading(true);

    const load = () => {
      fetchJson<TeamStatus>(`${API_BASE}/team-status/${teamId}`)
        .then(setStatus)
        .catch(console.error)
        .finally(() => setLoading(false));
    };

    load();
    const timer = setInterval(load, intervalMs);
    return () => clearInterval(timer);
  }, [teamId, intervalMs]);

  return { status, loading };
}
