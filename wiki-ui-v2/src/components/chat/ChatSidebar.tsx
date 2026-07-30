/**
 * ChatSidebar — 会话列表侧栏
 *
 * 功能：
 *   - 展示后端持久化会话列表（标题 + 更新时间 + 消息数）
 *   - 「+ 新建对话」按钮
 *   - hover 菜单：重命名 / 删除
 *   - 双击标题进入重命名（inline edit）
 *   - 加载中骨架屏
 */

import { useState } from 'react';
import {
  Plus, MoreHorizontal, Pencil, Trash2, Loader2, MessageSquare,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { showConfirm } from '@/components/ui/confirm-dialog';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
    try {
      await onRename(id, v);
    } finally {
      setBusyId(null);
    }
  };

  const cancelEdit = () => { setEditingId(null); setEditValue(''); };

  const handleDelete = async (t: ThreadMeta) => {
    if (!(await showConfirm(`删除对话「${t.title || '未命名'}」？此操作不可撤销。`, { title: '确认删除', variant: 'destructive' }))) return;
    setBusyId(t.thread_id);
    try {
      await onDelete(t.thread_id);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="flex flex-col h-full w-[260px] flex-shrink-0 border-r border-border bg-card">
      <div className="p-3 border-b border-border">
        <Button
          variant="outline"
          className="w-full justify-start gap-2"
          onClick={onNew}
        >
          <Plus className="h-4 w-4" /> 新建对话
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {loading && threads.length === 0 ? (
          <div className="space-y-2 p-2">
            {[0, 1, 2].map(i => (
              <div key={i} className="h-12 rounded-md bg-muted/50 animate-pulse" />
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
                className={`group relative px-3 py-2.5 mb-1 rounded-lg cursor-pointer transition-colors ${
                  isActive ? 'bg-accent' : 'hover:bg-accent/50'
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
                    <div className="flex items-center justify-between gap-1">
                      <div className="text-sm truncate font-medium pr-1">
                        {t.title || '未命名对话'}
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          render={
                            <button
                              className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-1 rounded hover:bg-accent-foreground/10 transition-opacity"
                              onClick={e => e.stopPropagation()}
                            />
                          }
                        >
                          {isBusy
                            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                            : <MoreHorizontal className="h-3.5 w-3.5" />}
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-32">
                          <DropdownMenuItem onClick={e => { e.stopPropagation(); startEdit(t); }}>
                            <Pencil className="h-3.5 w-3.5 mr-2" /> 重命名
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={e => { e.stopPropagation(); handleDelete(t); }}
                            className="text-destructive focus:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5 mr-2" /> 删除
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    <div className="text-xs text-muted-foreground mt-0.5 truncate">
                      {formatDate(t.updated_at)} · {t.message_count} 条消息
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
