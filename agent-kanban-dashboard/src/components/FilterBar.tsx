import { useState, useEffect, useCallback } from 'react';
import { Filter, Search, AlertTriangle, Eye, EyeOff, X } from 'lucide-react';
import type { FilterState, Priority } from '../types/kanban';
import { PRIORITY_CONFIG } from '../types/kanban';

interface Props {
  filterState: FilterState;
  onFilterChange: (state: FilterState) => void;
  assignees: string[];
  showEmptyColumns: boolean;
  onToggleEmptyColumns: () => void;
}

const PRIORITIES: (Priority | null)[] = [null, 'Critical', 'High', 'Medium', 'Low'];

const INITIAL_FILTER: FilterState = {
  priority: null,
  assignee: null,
  blockedOnly: false,
  search: '',
};

export default function FilterBar({
  filterState,
  onFilterChange,
  assignees,
  showEmptyColumns,
  onToggleEmptyColumns,
}: Props) {
  const update = (patch: Partial<FilterState>) =>
    onFilterChange({ ...filterState, ...patch });

  // Debounced search
  const [searchInput, setSearchInput] = useState(filterState.search);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== filterState.search) {
        update({ search: searchInput });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Sync external changes
  useEffect(() => {
    setSearchInput(filterState.search);
  }, [filterState.search]);

  const hasActiveFilter =
    filterState.priority !== null ||
    filterState.assignee !== null ||
    filterState.blockedOnly ||
    filterState.search !== '';

  const resetFilters = useCallback(() => {
    onFilterChange(INITIAL_FILTER);
    setSearchInput('');
  }, [onFilterChange]);

  return (
    <div className="bg-white border-b border-gray-200 px-6 py-2 flex items-center gap-4 flex-wrap">
      {/* Label */}
      <div className="flex items-center gap-1.5 text-gray-500">
        <Filter size={14} />
        <span className="text-xs font-medium">Filters</span>
      </div>

      {/* Priority Buttons */}
      <div className="flex items-center gap-1">
        {PRIORITIES.map((p) => {
          const isActive = filterState.priority === p;
          const label = p ?? 'All';
          const config = p ? PRIORITY_CONFIG[p] : null;
          return (
            <button
              key={label}
              onClick={() => update({ priority: p })}
              className={`text-[11px] font-medium px-2 py-1 rounded transition-colors cursor-pointer ${
                isActive
                  ? config
                    ? `${config.bg} ${config.color}`
                    : 'bg-gray-800 text-white'
                  : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
              }`}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200" />

      {/* Assignee Dropdown */}
      <select
        value={filterState.assignee ?? ''}
        onChange={(e) => update({ assignee: e.target.value || null })}
        className="text-xs border border-gray-200 rounded px-2 py-1 bg-white text-gray-600 focus:outline-none focus:ring-1 focus:ring-blue-300"
      >
        <option value="">All Assignees</option>
        {assignees.map((a) => (
          <option key={a} value={a}>{a}</option>
        ))}
      </select>

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200" />

      {/* Blocker Toggle */}
      <button
        onClick={() => update({ blockedOnly: !filterState.blockedOnly })}
        className={`text-[11px] font-medium px-2 py-1 rounded inline-flex items-center gap-1 transition-colors cursor-pointer ${
          filterState.blockedOnly
            ? 'bg-red-100 text-red-700'
            : 'bg-gray-100 text-gray-500 hover:bg-gray-200'
        }`}
      >
        <AlertTriangle size={11} />
        Blocked Only
      </button>

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200" />

      {/* Empty Columns Toggle */}
      <button
        onClick={onToggleEmptyColumns}
        className={`text-[11px] font-medium px-2 py-1 rounded inline-flex items-center gap-1 transition-colors cursor-pointer ${
          showEmptyColumns
            ? 'bg-gray-100 text-gray-500 hover:bg-gray-200'
            : 'bg-blue-100 text-blue-700'
        }`}
      >
        {showEmptyColumns ? <Eye size={11} /> : <EyeOff size={11} />}
        {showEmptyColumns ? 'All Columns' : 'Hide Empty'}
      </button>

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200" />

      {/* Search */}
      <div className="relative flex items-center">
        <Search size={13} className="absolute left-2 text-gray-400" />
        <input
          type="text"
          placeholder="Search tasks..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="text-xs border border-gray-200 rounded pl-7 pr-2 py-1 w-44 bg-white text-gray-600 placeholder-gray-400 focus:outline-none focus:ring-1 focus:ring-blue-300"
        />
      </div>

      {/* Reset Filters */}
      {hasActiveFilter && (
        <button
          onClick={resetFilters}
          className="text-[11px] font-medium px-2 py-1 rounded inline-flex items-center gap-1 text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors cursor-pointer"
        >
          <X size={11} />
          Reset
        </button>
      )}
    </div>
  );
}
