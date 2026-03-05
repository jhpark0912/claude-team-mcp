import { Ban, User, Users, MessageSquare, Clock } from 'lucide-react';
import Markdown from 'react-markdown';
import { useTaskDetail } from '@/hooks/useKanban';
import { PRIORITY_CONFIG, STATUS_CONFIG } from '@/types/kanban';
import { PRIORITY_ICONS, NOTE_TYPE_STYLES, NOTE_TYPE_LABELS } from '@/constants/ui';
import { STATUS_ICON_CONFIG } from '@/constants/ui';
import type { TaskNote } from '@/types/kanban';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';

interface Props {
  taskId: string | null;
  onClose: () => void;
}

export default function TaskDetailDialog({ taskId, onClose }: Props) {
  const { task, loading } = useTaskDetail(taskId);

  const activityNotes = task?.notes.filter((n) => n.note_type !== 'system') ?? [];
  const historyNotes = task?.notes.filter((n) => n.note_type === 'system') ?? [];

  return (
    <Dialog open={!!taskId} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col p-0 gap-0">
        {loading || !task ? (
          <div className="p-8 text-center text-muted-foreground">로딩 중...</div>
        ) : (
          <>
            {/* Header */}
            <DialogHeader className="px-6 pt-5 pb-3">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                {(() => {
                  const { icon: StatusIcon, color } = STATUS_ICON_CONFIG[task.status];
                  return (
                    <Badge variant="outline" className={`gap-1 ${color}`}>
                      <StatusIcon size={12} />
                      {STATUS_CONFIG[task.status].label}
                    </Badge>
                  );
                })()}
                {(() => {
                  const PIcon = PRIORITY_ICONS[task.priority];
                  const pc = PRIORITY_CONFIG[task.priority];
                  return (
                    <Badge variant="outline" className={`gap-1 ${pc.color}`}>
                      <PIcon size={12} />
                      {task.priority}
                    </Badge>
                  );
                })()}
                {task.is_blocked && (
                  <Badge variant="destructive" className="gap-1">
                    <Ban size={12} />BLOCKED
                  </Badge>
                )}
                <span className="ml-auto text-[10px] text-muted-foreground">v{task.version}</span>
              </div>
              <DialogTitle className="text-lg font-bold text-foreground">
                {task.title}
              </DialogTitle>
              <DialogDescription className="sr-only">
                태스크 상세 정보
              </DialogDescription>
            </DialogHeader>

            <Separator />

            {/* Tabs */}
            <Tabs defaultValue="overview" className="flex-1 flex flex-col min-h-0">
              <TabsList className="mx-6 mt-2 w-fit">
                <TabsTrigger value="overview" className="text-xs">개요</TabsTrigger>
                <TabsTrigger value="activity" className="text-xs">
                  활동 {activityNotes.length > 0 && `(${activityNotes.length})`}
                </TabsTrigger>
                <TabsTrigger value="history" className="text-xs">
                  히스토리 {historyNotes.length > 0 && `(${historyNotes.length})`}
                </TabsTrigger>
              </TabsList>

              <ScrollArea className="flex-1 min-h-0">
                <TabsContent value="overview" className="px-6 pb-4 mt-0">
                  <div className="space-y-4 pt-3">
                    {/* Meta */}
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="flex items-center gap-1.5">
                        <User size={12} className="text-muted-foreground" />
                        <span className="text-muted-foreground">담당자:</span>
                        <span className="font-medium text-foreground">
                          {task.assigned_to ? `${task.assigned_to.name} (${task.assigned_to.role})` : '미배정'}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <Users size={12} className="text-muted-foreground" />
                        <span className="text-muted-foreground">팀:</span>
                        <span className="font-medium text-foreground">{task.team.name}</span>
                      </div>
                      {task.blocker_reason && (
                        <div className="col-span-2 flex items-start gap-1.5">
                          <Ban size={12} className="text-red-400 mt-0.5" />
                          <span className="text-red-400">블로커:</span>
                          <span className="font-medium text-red-400">{task.blocker_reason}</span>
                        </div>
                      )}
                    </div>

                    {/* Description */}
                    {task.description && (
                      <div>
                        <h3 className="text-sm font-semibold text-muted-foreground mb-2">설명</h3>
                        <div className="prose prose-sm prose-invert max-w-full text-foreground break-words overflow-hidden">
                          <Markdown>{task.description}</Markdown>
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="activity" className="px-6 pb-4 mt-0">
                  <div className="pt-3">
                    <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                      <MessageSquare size={14} />활동 노트
                    </h3>
                    {activityNotes.length === 0 ? (
                      <p className="text-sm text-muted-foreground text-center py-8">활동 노트 없음</p>
                    ) : (
                      <div className="space-y-2">
                        {activityNotes.map((note) => (
                          <NoteItem key={note.id} note={note} />
                        ))}
                      </div>
                    )}
                  </div>
                </TabsContent>

                <TabsContent value="history" className="px-6 pb-4 mt-0">
                  <div className="pt-3">
                    <h3 className="text-sm font-semibold text-muted-foreground mb-3 flex items-center gap-1.5">
                      <Clock size={14} />상태 히스토리
                    </h3>
                    {historyNotes.length === 0 ? (
                      <p className="text-sm text-muted-foreground text-center py-8">히스토리 없음</p>
                    ) : (
                      <div className="relative pl-6">
                        <div className="absolute left-2 top-1 bottom-1 w-0.5 bg-border" />
                        <div className="space-y-3">
                          {historyNotes.map((note) => (
                            <div key={note.id} className="relative">
                              <div className="absolute -left-4 top-1.5 w-2 h-2 rounded-full bg-muted-foreground ring-2 ring-background" />
                              <div className="text-xs text-muted-foreground mb-0.5">
                                {new Date(note.created_at).toLocaleString()}
                              </div>
                              <div className="text-sm text-foreground break-words overflow-hidden">
                                <Markdown>{note.content}</Markdown>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </TabsContent>
              </ScrollArea>
            </Tabs>

            {/* Footer */}
            <Separator />
            <div className="px-6 py-3 text-xs text-muted-foreground">
              생성: {new Date(task.created_at).toLocaleString()}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function NoteItem({ note }: { note: TaskNote }) {
  const style = NOTE_TYPE_STYLES[note.note_type] || NOTE_TYPE_STYLES.system;
  const label = NOTE_TYPE_LABELS[note.note_type] || note.note_type;

  return (
    <div className={`rounded-md px-3 py-2 ${style}`}>
      <div className="flex items-center justify-between mb-0.5">
        <span className="text-[11px] font-semibold">{note.agent}</span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] opacity-60">{label}</span>
          <span className="text-[10px] opacity-60">
            {new Date(note.created_at).toLocaleTimeString()}
          </span>
        </div>
      </div>
      <div className="text-xs leading-relaxed prose prose-sm prose-invert max-w-full break-words overflow-hidden">
        <Markdown>{note.content}</Markdown>
      </div>
    </div>
  );
}
