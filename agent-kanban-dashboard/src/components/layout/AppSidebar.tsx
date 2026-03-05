import { RefreshCw, BarChart3, Users, AlertTriangle, Clock, LayoutDashboard } from 'lucide-react';
import type { Team, TeamStatus as TeamStatusType } from '@/types/kanban';
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
} from '@/components/ui/sidebar';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ChevronDown } from 'lucide-react';
import StatusSummary from '@/components/sidebar/StatusSummary';
import AgentList from '@/components/sidebar/AgentList';
import BlockerList from '@/components/sidebar/BlockerList';
import ActivityFeed from '@/components/sidebar/ActivityFeed';

interface Props {
  teams: Team[];
  selectedTeamId: string | null;
  onTeamChange: (id: string) => void;
  teamStatus: TeamStatusType | null;
  onRefresh: () => void;
  updatedAt: string | null;
  selectedAssignee: string | null;
  onAgentClick: (name: string) => void;
}

export default function AppSidebar({
  teams,
  selectedTeamId,
  onTeamChange,
  teamStatus,
  onRefresh,
  updatedAt,
  selectedAssignee,
  onAgentClick,
}: Props) {
  return (
    <Sidebar>
      <SidebarHeader className="border-b border-sidebar-border px-4 py-3">
        <div className="flex items-center gap-2 mb-3">
          <LayoutDashboard size={20} className="text-primary" />
          <span className="font-semibold text-sm text-sidebar-foreground">AI-Board</span>
        </div>
        <Select value={selectedTeamId ?? ''} onValueChange={onTeamChange}>
          <SelectTrigger className="w-full h-8 text-xs">
            <SelectValue placeholder="팀 선택" />
          </SelectTrigger>
          <SelectContent>
            {teams.map((t) => (
              <SelectItem key={t.id} value={t.id} className="text-xs">
                {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </SidebarHeader>

      <SidebarContent className="px-2">
        {teamStatus ? (
          <>
            <SidebarSection icon={<BarChart3 size={14} />} label="상태 요약" defaultOpen>
              <StatusSummary teamStatus={teamStatus} />
            </SidebarSection>

            <SidebarSection icon={<Users size={14} />} label="에이전트" defaultOpen>
              <AgentList
                agents={teamStatus.agents}
                selectedAssignee={selectedAssignee}
                onAgentClick={onAgentClick}
              />
            </SidebarSection>

            {teamStatus.blockers.length > 0 && (
              <SidebarSection
                icon={<AlertTriangle size={14} className="text-red-400" />}
                label={`블로커 (${teamStatus.blockers.length})`}
                defaultOpen
              >
                <BlockerList blockers={teamStatus.blockers} />
              </SidebarSection>
            )}

            <SidebarSection icon={<Clock size={14} />} label="최근 활동" defaultOpen={false}>
              <ActivityFeed activities={teamStatus.recent_activity} />
            </SidebarSection>
          </>
        ) : (
          <SidebarGroup>
            <SidebarGroupContent>
              <p className="text-xs text-muted-foreground px-2 py-4">로딩 중...</p>
            </SidebarGroupContent>
          </SidebarGroup>
        )}
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border px-4 py-2">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">
            {updatedAt
              ? new Date(updatedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
              : '—'}
          </span>
          <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onRefresh}>
            <RefreshCw size={12} />
          </Button>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}

function SidebarSection({
  icon,
  label,
  defaultOpen = true,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Collapsible defaultOpen={defaultOpen} className="group/collapsible">
      <SidebarGroup>
        <SidebarGroupLabel asChild>
          <CollapsibleTrigger className="flex w-full items-center gap-1.5 text-xs font-semibold cursor-pointer hover:text-foreground">
            {icon}
            <span className="flex-1 text-left">{label}</span>
            <ChevronDown size={14} className="transition-transform group-data-[state=closed]/collapsible:rotate-[-90deg]" />
          </CollapsibleTrigger>
        </SidebarGroupLabel>
        <CollapsibleContent>
          <SidebarGroupContent className="pt-1">
            {children}
          </SidebarGroupContent>
        </CollapsibleContent>
      </SidebarGroup>
    </Collapsible>
  );
}
