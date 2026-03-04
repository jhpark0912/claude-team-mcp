import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { Activity } from '@/types/kanban';

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
    const prevMinute = prev.at.slice(0, 16);
    const currMinute = curr.at.slice(0, 16);

    if (curr.agent === prev.agent && currMinute === prevMinute) {
      currentGroup.push(curr);
    } else {
      if (currentGroup.length > 1) {
        result.push({ agent: currentGroup[0].agent, minute: currentGroup[0].at, items: currentGroup });
      } else {
        result.push(currentGroup[0]);
      }
      currentGroup = [curr];
    }
  }

  if (currentGroup.length > 1) {
    result.push({ agent: currentGroup[0].agent, minute: currentGroup[0].at, items: currentGroup });
  } else if (currentGroup.length === 1) {
    result.push(currentGroup[0]);
  }

  return result;
}

function isGroup(entry: Activity | ActivityGroup): entry is ActivityGroup {
  return 'items' in entry;
}

interface Props {
  activities: Activity[];
}

export default function ActivityFeed({ activities }: Props) {
  const grouped = groupActivities(activities.slice(0, 15));

  if (grouped.length === 0) {
    return <p className="text-xs text-muted-foreground">최근 활동 없음</p>;
  }

  return (
    <div className="space-y-0.5">
      {grouped.map((entry, i) =>
        isGroup(entry) ? (
          <ActivityGroupItem key={i} group={entry} />
        ) : (
          <ActivityItem key={i} activity={entry} />
        )
      )}
    </div>
  );
}

function ActivityItem({ activity }: { activity: Activity }) {
  return (
    <div className="flex gap-2 py-1.5 border-b border-border last:border-0">
      <span className="text-[11px] text-muted-foreground whitespace-nowrap w-14 flex-shrink-0">
        {new Date(activity.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
      </span>
      <div className="min-w-0">
        <span className="text-[11px] font-medium text-foreground">{activity.agent}</span>
        <p className="text-[11px] text-muted-foreground truncate">{activity.detail}</p>
      </div>
    </div>
  );
}

function ActivityGroupItem({ group }: { group: ActivityGroup }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex gap-2 py-1.5 cursor-pointer hover:bg-accent rounded"
      >
        <span className="text-[11px] text-muted-foreground whitespace-nowrap w-14 flex-shrink-0">
          {new Date(group.minute).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
        <div className="min-w-0 flex items-center gap-1">
          {expanded ? (
            <ChevronDown size={11} className="text-muted-foreground flex-shrink-0" />
          ) : (
            <ChevronRight size={11} className="text-muted-foreground flex-shrink-0" />
          )}
          <span className="text-[11px] font-medium text-foreground">{group.agent}</span>
          <span className="text-[11px] text-muted-foreground">— {group.items.length}개 변경</span>
        </div>
      </button>
      {expanded && (
        <div className="ml-16 pl-2 border-l-2 border-border space-y-0.5 pb-1">
          {group.items.map((act, i) => (
            <p key={i} className="text-[11px] text-muted-foreground truncate">{act.detail}</p>
          ))}
        </div>
      )}
    </div>
  );
}
