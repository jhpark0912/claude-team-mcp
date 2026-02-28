import { useState } from 'react';
import { BarChart3, Users, AlertTriangle, Clock, ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';
import type { TeamStatus, Activity } from '../types/kanban';
import { ALL_STATUSES, STATUS_CONFIG } from '../types/kanban';

interface Props {
  teamStatus: TeamStatus | null;
}

interface ActivityGroup {
  agent: string;
  minute: string;
  items: Activity[];
}

function groupActivities(activities: Activity[]): (Activity | ActivityGroup)[] {
  if (activities.length === 0) return [];

  const result: (Activity | ActivityGroup)[] = [];
  let currentGroup: Activity[] = [activities[0]];

  for (let i = 1; i < activities.length; i++) {
    const prev = activities[i - 1];
    const curr = activities[i];
    const prevMinute = prev.at.slice(0, 16); // YYYY-MM-DDTHH:MM
    const currMinute = curr.at.slice(0, 16);

    if (curr.agent === prev.agent && currMinute === prevMinute) {
      currentGroup.push(curr);
    } else {
      if (currentGroup.length > 1) {
        result.push({
          agent: currentGroup[0].agent,
          minute: currentGroup[0].at,
          items: currentGroup,
        });
      } else {
        result.push(currentGroup[0]);
      }
      currentGroup = [curr];
    }
  }

  if (currentGroup.length > 1) {
    result.push({
      agent: currentGroup[0].agent,
      minute: currentGroup[0].at,
      items: currentGroup,
    });
  } else if (currentGroup.length === 1) {
    result.push(currentGroup[0]);
  }

  return result;
}

function isGroup(entry: Activity | ActivityGroup): entry is ActivityGroup {
  return 'items' in entry;
}

export default function SidePanel({ teamStatus }: Props) {
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    status: true,
    agents: true,
    blockers: true,
    activity: true,
  });

  if (!teamStatus) {
    return <div className="text-sm text-gray-400">Loading status...</div>;
  }

  const toggleSection = (key: string) => {
    setOpenSections((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const grouped = groupActivities(teamStatus.recent_activity.slice(0, 15));

  return (
    <div className="space-y-5">
      {/* Status Summary */}
      <section>
        <SectionHeader
          icon={<BarChart3 size={14} />}
          label="Status Summary"
          open={openSections.status}
          onToggle={() => toggleSection('status')}
        />
        {openSections.status && (
          <div className="space-y-1.5">
            {ALL_STATUSES.map((status) => {
              const total = Object.values(teamStatus.summary).reduce((a, b) => a + b, 0);
              const count = teamStatus.summary[status];
              const pct = total > 0 ? (count / total) * 100 : 0;
              const dimmed = count === 0;
              return (
                <div key={status} className={`flex items-center gap-2 ${dimmed ? 'opacity-40' : ''}`}>
                  <span className="text-xs text-gray-500 w-20 truncate">{STATUS_CONFIG[status].label}</span>
                  <div className="flex-1 bg-gray-100 rounded-full h-4 overflow-hidden">
                    <div
                      className={`${STATUS_CONFIG[status].color} h-full rounded-full transition-all duration-500`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-xs font-medium text-gray-600 w-6 text-right">{count}</span>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* Agent Workload */}
      <section>
        <SectionHeader
          icon={<Users size={14} />}
          label="Agents"
          open={openSections.agents}
          onToggle={() => toggleSection('agents')}
        />
        {openSections.agents && (
          <div className="space-y-1.5">
            {teamStatus.agents.map((agent) => (
              <div key={agent.name} className="flex items-center justify-between bg-gray-50 rounded-md px-3 py-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-gray-700">{agent.name}</span>
                  <span className="text-[10px] bg-gray-200 text-gray-500 px-1.5 py-0.5 rounded-full">{agent.role}</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                    {agent.in_progress} active
                  </span>
                  <span className="text-gray-400">{agent.total} total</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Blockers */}
      {teamStatus.blockers.length > 0 && (
        <section>
          <SectionHeader
            icon={<AlertTriangle size={14} className="text-red-600" />}
            label={`Blockers (${teamStatus.blockers.length})`}
            open={openSections.blockers}
            onToggle={() => toggleSection('blockers')}
            className="text-red-600"
          />
          {openSections.blockers && (
            <div className="space-y-1.5">
              {teamStatus.blockers.map((b) => (
                <div key={b.task_id} className="bg-red-50 border border-red-200 rounded-md px-3 py-2">
                  <p className="text-xs font-medium text-red-800">{b.title}</p>
                  <p className="text-[11px] text-red-600 mt-0.5">{b.reason}</p>
                  {b.assigned_to && (
                    <span className="text-[10px] text-red-400">{b.assigned_to}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Recent Activity */}
      <section>
        <SectionHeader
          icon={<Clock size={14} />}
          label="Recent Activity"
          open={openSections.activity}
          onToggle={() => toggleSection('activity')}
        />
        {openSections.activity && (
          <div className="space-y-1">
            {grouped.length === 0 ? (
              <p className="text-xs text-gray-400">No recent activity</p>
            ) : (
              grouped.map((entry, i) =>
                isGroup(entry) ? (
                  <ActivityGroupItem key={i} group={entry} />
                ) : (
                  <ActivityItem key={i} activity={entry} />
                )
              )
            )}
          </div>
        )}
      </section>
    </div>
  );
}

function SectionHeader({
  icon,
  label,
  open,
  onToggle,
  className = 'text-gray-700',
}: {
  icon: React.ReactNode;
  label: string;
  open: boolean;
  onToggle: () => void;
  className?: string;
}) {
  return (
    <button
      onClick={onToggle}
      className={`w-full text-sm font-semibold mb-2 flex items-center gap-1.5 cursor-pointer hover:opacity-80 ${className}`}
    >
      {icon}
      <span className="flex-1 text-left">{label}</span>
      {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
    </button>
  );
}

function ActivityItem({ activity }: { activity: Activity }) {
  return (
    <div className="flex gap-2 py-1.5 border-b border-gray-100 last:border-0">
      <span className="text-[11px] text-gray-400 whitespace-nowrap w-14 flex-shrink-0">
        {new Date(activity.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </span>
      <div className="min-w-0">
        <span className="text-[11px] font-medium text-gray-700">{activity.agent}</span>
        <p className="text-[11px] text-gray-500 truncate">{activity.detail}</p>
      </div>
    </div>
  );
}

function ActivityGroupItem({ group }: { group: ActivityGroup }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b border-gray-100 last:border-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex gap-2 py-1.5 cursor-pointer hover:bg-gray-50 rounded"
      >
        <span className="text-[11px] text-gray-400 whitespace-nowrap w-14 flex-shrink-0">
          {new Date(group.minute).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
        <div className="min-w-0 flex items-center gap-1">
          {expanded ? <ChevronDown size={11} className="text-gray-400 flex-shrink-0" /> : <ChevronRight size={11} className="text-gray-400 flex-shrink-0" />}
          <span className="text-[11px] font-medium text-gray-700">{group.agent}</span>
          <span className="text-[11px] text-gray-400">— {group.items.length}개 상태 변경</span>
        </div>
      </button>
      {expanded && (
        <div className="ml-16 pl-2 border-l-2 border-gray-200 space-y-0.5 pb-1">
          {group.items.map((act, i) => (
            <p key={i} className="text-[11px] text-gray-500 truncate">{act.detail}</p>
          ))}
        </div>
      )}
    </div>
  );
}
