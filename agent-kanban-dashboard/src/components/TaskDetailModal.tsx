import { useState, useEffect } from 'react';
import { Ban, User, Users, MessageSquare, X, Clock } from 'lucide-react';
import Markdown from 'react-markdown';
import { useTaskDetail } from '../hooks/useKanban';
import { PRIORITY_CONFIG, STATUS_CONFIG } from '../types/kanban';
import { PRIORITY_ICONS, NOTE_TYPE_STYLES } from '../constants/ui';
import type { TaskNote } from '../types/kanban';

type Tab = 'overview' | 'activity' | 'history';

interface Props {
  taskId: string;
  onClose: () => void;
}

export default function TaskDetailModal({ taskId, onClose }: Props) {
  const { task, loading } = useTaskDetail(taskId);
  const [activeTab, setActiveTab] = useState<Tab>('overview');

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  const activityNotes = task?.notes.filter((n) => n.note_type !== 'system') ?? [];
  const historyNotes = task?.notes.filter((n) => n.note_type === 'system') ?? [];

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'overview', label: 'Overview' },
    { key: 'activity', label: 'Activity', count: activityNotes.length },
    { key: 'history', label: 'History', count: historyNotes.length },
  ];

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {loading || !task ? (
          <div className="p-8 text-center text-gray-400">Loading...</div>
        ) : (
          <>
            {/* Header */}
            <div className="px-6 py-4 border-b border-gray-200">
              <div className="flex items-center gap-2 mb-2">
                <span className={`text-xs font-semibold px-2 py-0.5 rounded ${STATUS_CONFIG[task.status].color}`}>
                  {STATUS_CONFIG[task.status].label}
                </span>
                {(() => {
                  const Icon = PRIORITY_ICONS[task.priority as keyof typeof PRIORITY_ICONS];
                  return (
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded flex items-center gap-1 ${PRIORITY_CONFIG[task.priority].bg} ${PRIORITY_CONFIG[task.priority].color}`}>
                      <Icon size={12} />{task.priority}
                    </span>
                  );
                })()}
                {task.is_blocked && (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded bg-red-100 text-red-700 flex items-center gap-1">
                    <Ban size={12} />BLOCKED
                  </span>
                )}
                <span className="ml-auto text-xs text-gray-400">v{task.version}</span>
              </div>
              <h2 className="text-lg font-bold text-gray-800">{task.title}</h2>
            </div>

            {/* Tabs */}
            <div className="px-6 border-b border-gray-200 flex gap-4">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`py-2 text-sm font-medium border-b-2 transition-colors cursor-pointer ${
                    activeTab === tab.key
                      ? 'border-blue-500 text-blue-600'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  {tab.label}
                  {tab.count !== undefined && (
                    <span className="ml-1 text-xs text-gray-400">({tab.count})</span>
                  )}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              {activeTab === 'overview' && (
                <div className="space-y-4">
                  {/* Meta */}
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <span className="text-gray-400 inline-flex items-center gap-1"><User size={12} />Assignee: </span>
                      <span className="font-medium">
                        {task.assigned_to ? `${task.assigned_to.name} (${task.assigned_to.role})` : 'Unassigned'}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400 inline-flex items-center gap-1"><Users size={12} />Team: </span>
                      <span className="font-medium">{task.team.name}</span>
                    </div>
                    {task.blocker_reason && (
                      <div className="col-span-2">
                        <span className="text-red-500">Blocker: </span>
                        <span className="font-medium text-red-700">{task.blocker_reason}</span>
                      </div>
                    )}
                  </div>

                  {/* Description */}
                  {task.description && (
                    <div>
                      <h3 className="text-sm font-semibold text-gray-600 mb-2">Description</h3>
                      <div className="prose prose-sm max-w-none text-gray-700">
                        <Markdown>{task.description}</Markdown>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'activity' && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-600 mb-3 flex items-center gap-1.5">
                    <MessageSquare size={14} />Activity Notes
                  </h3>
                  {activityNotes.length === 0 ? (
                    <p className="text-sm text-gray-400 text-center py-8">No activity notes yet</p>
                  ) : (
                    <div className="space-y-2">
                      {activityNotes.map((note) => (
                        <NoteItem key={note.id} note={note} />
                      ))}
                    </div>
                  )}
                </div>
              )}

              {activeTab === 'history' && (
                <div>
                  <h3 className="text-sm font-semibold text-gray-600 mb-3 flex items-center gap-1.5">
                    <Clock size={14} />Status History
                  </h3>
                  {historyNotes.length === 0 ? (
                    <p className="text-sm text-gray-400 text-center py-8">No history yet</p>
                  ) : (
                    <div className="relative pl-6">
                      {/* Timeline line */}
                      <div className="absolute left-2 top-1 bottom-1 w-0.5 bg-gray-200" />
                      <div className="space-y-3">
                        {historyNotes.map((note) => (
                          <div key={note.id} className="relative">
                            {/* Timeline dot */}
                            <div className="absolute -left-4 top-1.5 w-2 h-2 rounded-full bg-gray-400 ring-2 ring-white" />
                            <div className="text-xs text-gray-400 mb-0.5">
                              {new Date(note.created_at).toLocaleString()}
                            </div>
                            <div className="text-sm text-gray-700">
                              <Markdown>{note.content}</Markdown>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-6 py-3 border-t border-gray-200 flex justify-between text-xs text-gray-400">
              <span>Created: {new Date(task.created_at).toLocaleString()}</span>
              <button
                onClick={onClose}
                className="px-3 py-1 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 transition-colors cursor-pointer flex items-center gap-1"
              >
                <X size={14} />Close
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function NoteItem({ note }: { note: TaskNote }) {
  const style = NOTE_TYPE_STYLES[note.note_type] || NOTE_TYPE_STYLES.system;

  return (
    <div className={`rounded-md px-3 py-2 ${style}`}>
      <div className="flex items-center justify-between mb-0.5">
        <span className="text-[11px] font-semibold">{note.agent}</span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] opacity-60">{note.note_type}</span>
          <span className="text-[10px] opacity-60">
            {new Date(note.created_at).toLocaleTimeString()}
          </span>
        </div>
      </div>
      <div className="text-xs leading-relaxed prose prose-sm max-w-none">
        <Markdown>{note.content}</Markdown>
      </div>
    </div>
  );
}
