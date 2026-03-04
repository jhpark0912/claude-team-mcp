import { useState, useEffect, useCallback } from 'react';
import { Search, AlertTriangle, X } from 'lucide-react';
import type { FilterState, Priority } from '@/types/kanban';
import { PRIORITY_CONFIG } from '@/types/kanban';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Separator } from '@/components/ui/separator';

interface Props {
  filterState: FilterState;
  onFilterChange: (state: FilterState) => void;
  assignees: string[];
}

const PRIORITIES: (Priority | null)[] = [null, 'Critical', 'High', 'Medium', 'Low'];

const INITIAL_FILTER: FilterState = {
  priority: null,
  assignee: null,
  blockedOnly: false,
  search: '',
};

export default function BoardToolbar({ filterState, onFilterChange, assignees }: Props) {
  const update = (patch: Partial<FilterState>) =>
    onFilterChange({ ...filterState, ...patch });

  const [searchInput, setSearchInput] = useState(filterState.search);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== filterState.search) {
        update({ search: searchInput });
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

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
    <div className="flex items-center gap-2 px-4 py-2 border-b border-border shrink-0">
      {/* Priority Toggle Group */}
      <ToggleGroup
        type="single"
        value={filterState.priority ?? 'all'}
        onValueChange={(val) => update({ priority: val === 'all' ? null : (val as Priority) })}
        className="gap-0.5"
      >
        {PRIORITIES.map((p) => {
          const label = p ?? '전체';
          const config = p ? PRIORITY_CONFIG[p] : null;
          return (
            <ToggleGroupItem
              key={p ?? 'all'}
              value={p ?? 'all'}
              size="sm"
              className={`text-[11px] px-2 h-7 ${
                config ? `data-[state=on]:${config.bg} data-[state=on]:${config.color}` : ''
              }`}
            >
              {label}
            </ToggleGroupItem>
          );
        })}
      </ToggleGroup>

      <Separator orientation="vertical" className="h-5" />

      {/* Assignee Select */}
      <Select
        value={filterState.assignee ?? '__all__'}
        onValueChange={(val) => update({ assignee: val === '__all__' ? null : val })}
      >
        <SelectTrigger className="w-[140px] h-7 text-xs">
          <SelectValue placeholder="전체 담당자" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__all__" className="text-xs">전체 담당자</SelectItem>
          {assignees.map((a) => (
            <SelectItem key={a} value={a} className="text-xs">{a}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Separator orientation="vertical" className="h-5" />

      {/* Blocker Toggle */}
      <Button
        variant={filterState.blockedOnly ? 'destructive' : 'ghost'}
        size="sm"
        className="h-7 text-[11px] gap-1"
        onClick={() => update({ blockedOnly: !filterState.blockedOnly })}
      >
        <AlertTriangle size={11} />
        블로커만
      </Button>

      <Separator orientation="vertical" className="h-5" />

      {/* Search */}
      <div className="relative flex items-center ml-auto">
        <Search size={13} className="absolute left-2 text-muted-foreground" />
        <Input
          type="text"
          placeholder="검색..."
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          className="h-7 text-xs pl-7 w-32"
        />
      </div>

      {/* Reset */}
      {hasActiveFilter && (
        <Button
          variant="ghost"
          size="sm"
          className="h-7 text-[11px] gap-1 text-muted-foreground"
          onClick={resetFilters}
        >
          <X size={11} />
          초기화
        </Button>
      )}
    </div>
  );
}
