import { useState, useCallback } from 'react';
import type { Status } from '@/types/kanban';
import {
  ALL_STATUSES,
  COLUMN_CARD_LIMITS,
  DEFAULT_COLLAPSED,
  CARD_LOAD_INCREMENT,
} from '@/types/kanban';

interface ColumnState {
  collapsed: Record<Status, boolean>;
  visibleCounts: Record<Status, number>;
  toggleCollapse: (status: Status) => void;
  showMore: (status: Status) => void;
  isCollapsed: (status: Status) => boolean;
  getVisibleCount: (status: Status) => number;
}

function buildInitialCollapsed(): Record<Status, boolean> {
  const result = {} as Record<Status, boolean>;
  for (const s of ALL_STATUSES) {
    result[s] = DEFAULT_COLLAPSED.includes(s);
  }
  return result;
}

function buildInitialVisibleCounts(): Record<Status, number> {
  const result = {} as Record<Status, number>;
  for (const s of ALL_STATUSES) {
    result[s] = COLUMN_CARD_LIMITS[s];
  }
  return result;
}

export function useColumnState(): ColumnState {
  const [collapsed, setCollapsed] = useState<Record<Status, boolean>>(buildInitialCollapsed);
  const [visibleCounts, setVisibleCounts] = useState<Record<Status, number>>(buildInitialVisibleCounts);

  const toggleCollapse = useCallback((status: Status) => {
    setCollapsed(prev => ({ ...prev, [status]: !prev[status] }));
    // 펼칠 때 visibleCount를 기본값으로 리셋
    setVisibleCounts(prev => ({
      ...prev,
      [status]: COLUMN_CARD_LIMITS[status],
    }));
  }, []);

  const showMore = useCallback((status: Status) => {
    setVisibleCounts(prev => ({
      ...prev,
      [status]: prev[status] + CARD_LOAD_INCREMENT,
    }));
  }, []);

  const isCollapsed = useCallback((status: Status) => collapsed[status], [collapsed]);
  const getVisibleCount = useCallback((status: Status) => visibleCounts[status], [visibleCounts]);

  return { collapsed, visibleCounts, toggleCollapse, showMore, isCollapsed, getVisibleCount };
}
