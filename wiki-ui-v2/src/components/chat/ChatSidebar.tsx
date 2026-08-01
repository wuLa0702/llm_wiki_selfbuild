/**
 * ChatSidebar — 会话列表侧栏
 *
 * 功能：
 *   - 「+ 新建对话」填充主按钮（顶部）
 *   - 会话列表：标题 + 时间 + 选中态 3px 左竖条 + 浅背景
 *   - hover 浮删/改名图标
 */

import { useState } from 'react';
import {
  Plus, Pencil, Trash2, Loader2, MessageSquare,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { showConfirm } from '@/components/ui/confirm-dialog';
import type { ThreadMeta } from '@/api/agent';

interface ChatSidebarProps {
  threads: ThreadMeta[];
  activeId: string;
  loading: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onRename: (id: string, newTitle: string) => Promise<void> | void;
  onDelete: (id: string) => Promise<void> | void;
}

function formatDate(ts: number): string {
  const d = new Date(ts * 1000);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  if (sameDay) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  const sameYear = d.getFullYear() === now.getFullYear();
  return d.toLocaleDateString('zh-CN', sameYear ? { month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short', day: 'numeric' });
}

export default function ChatSidebar({
  threads, activeId, loading, onSelect, onNew, onRename, onDelete,
}: ChatSidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const startEdit = (t: ThreadMeta) => {
    setEditingId(t.thread_id);
    setEditValue(t.title);
  };

  const commitEdit = async () => {
    const id = editingId;
    if (!id) return;
    const v = editValue.trim();
    setEditingId(null);
    if (!v) return;
    setBusyId(id);
    try { await onRename(id, v); } finally { setBusyId(null); }
  };

  const cancelEdit = () => { setEditingId(null); setEditValue(''); };

  const handleDelete = async (t: ThreadMeta) => {
    if (!(await showConfirm(`删除对话「${t.title || '未命名'}」？此操作不可撤销。`, { title: '确认删除', variant: 'destructive' }))) return;
    setBusyId(t.thread_id);
    try { await onDelete(t.thread_id); } finally { setBusyId(null); }
  };

  return (
    <div className="flex flex-col h-full w-[260px] flex-shrink-0 bg-sidebar border-r border-sidebar-border">
      {/* 顶部新建按钮 */}
      <div className="p-3 border-b border-sidebar-border">
        <Button
          className="w-full justify-start gap-2 press"
          onClick={onNew}
        >
          <Plus className="h-4 w-4" /> 新建对话
        </Button>
      </div>

      {/* 会话列表 */}
      <div className="flex-1 overflow-y-auto p-2 space-y-0.5">
        {loading && threads.length === 0 ? (
          <div className="space-y-2 p-2">
            {[0, 1, 2].map(i => (
              <div key={i} className="h-12 rounded-lg bg-muted/50 skeleton-pulse" />
            ))}
          </div>
        ) : threads.length === 0 ? (
          <div className="text-xs text-muted-foreground text-center py-8 px-2">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-40" />
            暂无对话记录
            <div className="mt-1 opacity-70">点击「新建对话」开始</div>
          </div>
        ) : (
          threads.map(t => {
            const isActive = t.thread_id === activeId;
            const isEditing = editingId === t.thread_id;
            const isBusy = busyId === t.thread_id;
            return (
              <div
                key={t.thread_id}
                className={`group relative flex items-center px-3 py-2.5 rounded-lg cursor-pointer transition-colors duration-150 ${
                  isActive
                    ? 'bg-sidebar-accent text-sidebar-accent-foreground border-l-3 border-sidebar-primary pl-[10px]'
                    : 'hover:bg-sidebar-accent/60'
                }`}
                onClick={() => { if (!isEditing && !isBusy) onSelect(t.thread_id); }}
                onDoubleClick={() => { if (!isBusy) startEdit(t); }}
                title="双击重命名"
              >
                {isEditing ? (
                  <Input
                    autoFocus
                    value={editValue}
                    onChange={e => setEditValue(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') commitEdit();
                      if (e.key === 'Escape') cancelEdit();
                    }}
                    onBlur={commitEdit}
                    maxLength={50}
                    className="h-7 text-sm py-0"
                    onClick={e => e.stopPropagation()}
                  />
                ) : (
                  <>
                    <div className="flex-1 min-w-0 pr-1">
                      <div className="text-sm truncate font-medium">
                        {t.title || '未命名对话'}
                      </div>
                      <div className="text-[11px] text-muted-foreground mt-0.5 truncate">
                        {formatDate(t.updated_at)}
                      </div>
                    </div>
                    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      {isBusy ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <>
                          <button
                            className="p-1 rounded hover:bg-foreground/10 transition-colors"
                            onClick={e => { e.stopPropagation(); startEdit(t); }}
                            title="重命名"
                          >
                            <Pencil className="h-3 w-3" />
                          </button>
                          <button
                            className="p-1 rounded hover:bg-destructive/20 text-destructive transition-colors"
                            onClick={e => { e.stopPropagation(); handleDelete(t); }}
                            title="删除"
                          >
                            <Trash2 className="h-3 w-3" />
                          </button>
                        </>
                      )}
                    </div>
                  </>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
