/**
 * ChatMessage — 单条消息渲染
 *
 * 用户消息：右对齐，主题色填充气泡 + 白色文字
 * 助手消息：左对齐，白底 + 细边框 + AI 头像，引用卡片，hover 浮操作按钮
 */

import { useState } from 'react';
import { Copy, Check, RefreshCw, ThumbsUp, ThumbsDown, FileText } from 'lucide-react';
import MarkdownRenderer from '@/components/shared/MarkdownRenderer';
import ToolCallBadge from './ToolCallBadge';
import type { ToolCallInfo } from './ToolCallBadge';
import type { ChatMessage as ApiChatMessage } from '@/api/agent';
import { showToast } from '@/components/shared/Toast';

interface ChatMessageProps {
  message: ApiChatMessage;
  /** 关联的工具调用列表（assistant 消息） */
  toolCalls?: ToolCallInfo[];
  isStreaming?: boolean;
  /** 引用数据（cited_pages） */
  citations?: CitationInfo[];
  onCopy?: (content: string) => void;
  onRegenerate?: () => void;
  /** wikilink 跳转回调 */
  onNavigate?: (path: string) => void;
  /** 引用卡片跳转回调 */
  onCitationClick?: (citation: CitationInfo) => void;
  /** 反馈回调 (rating: 'positive' | 'negative') */
  onFeedback?: (rating: 'positive' | 'negative') => void;
}

/** Mock 引用卡片类型 */
export interface CitationInfo {
  page_id: string;
  title: string;
  /** wiki 路径，用于跳转 */
  path?: string;
}

function mid() { return Math.random().toString(36).slice(2, 10); }

export default function ChatMessage({
  message, toolCalls, isStreaming, citations, onCopy, onRegenerate, onNavigate, onCitationClick, onFeedback,
}: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const [toolsExpanded, setToolsExpanded] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = () => {
    if (onCopy) onCopy(message.content);
    else navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const handleFeedback = (type: 'up' | 'down') => {
    onFeedback?.(type === 'up' ? 'positive' : 'negative');
  };

  // ── 用户消息 ──────────────────────────────────────────────────────────
  if (isUser) {
    return (
      <div className="flex gap-3 justify-end msg-enter">
        <div className="max-w-[80%] bg-primary text-primary-foreground rounded-[1.125rem] rounded-tr-md px-4 py-2.5 text-sm whitespace-pre-wrap break-words shadow-sm leading-relaxed">
          {message.content}
        </div>
      </div>
    );
  }

  // ── 助手消息 ──────────────────────────────────────────────────────────
  const { content } = message;
  const hasToolCalls = toolCalls && toolCalls.length > 0;

  return (
    <div className="flex gap-3 msg-enter">
      {/* AI 头像 */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-gradient-to-br from-primary/90 to-primary/70 text-primary-foreground flex items-center justify-center text-xs font-bold shadow-sm select-none">
        AI
      </div>

      <div className="flex-1 min-w-0 group/message">
        {/* 工具调用 — 折叠条 */}
        {hasToolCalls && (
          <div className="mb-2">
            <button
              onClick={() => setToolsExpanded(!toolsExpanded)}
              className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground hover:text-foreground bg-muted/60 hover:bg-muted rounded-full px-2.5 py-1 transition-colors"
            >
              {toolsExpanded ? '收起' : '展开'}
              <span className="font-medium">工具调用</span>
              <span className="bg-foreground/10 rounded-full px-1.5 text-[10px]">{toolCalls!.length}</span>
            </button>
            {toolsExpanded && (
              <div className="mt-1.5 space-y-1">
                {toolCalls!.map(tc => <ToolCallBadge key={tc.id} tool={tc} />)}
              </div>
            )}
          </div>
        )}

        {/* 正文 */}
        {content ? (
          <div className="space-y-2.5">
            <div className="bg-card border border-border rounded-[1.125rem] rounded-tl-md px-5 py-3.5 shadow-sm leading-relaxed">
              <MarkdownRenderer content={content} onNavigate={onNavigate} />

              {/* 引用卡片 */}
              {citations && citations.length > 0 && (
                <div className="mt-3 pt-3 border-t border-border/60 space-y-1.5">
                  <div className="text-[11px] font-medium text-muted-foreground mb-1.5">参考来源</div>
                  {citations.map((c, i) => (
                    <button
                      key={i}
                      className="flex items-center gap-2 w-full text-left p-2 rounded-lg bg-muted/40 hover:bg-muted transition-colors group/cite"
                      onClick={() => {
                        onCitationClick?.(c);
                      }}
                    >
                      <FileText className="h-3.5 w-3.5 text-type-source flex-shrink-0" />
                      <span className="text-xs font-medium truncate group-hover/cite:text-type-source transition-colors">
                        {c.title}
                      </span>
                      <span className="text-[10px] text-muted-foreground ml-auto flex-shrink-0">
                        {c.path}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* 操作按钮 — hover 时浮显 */}
            {!isStreaming && (
              <div className="flex items-center gap-1 pl-1 opacity-0 group-hover/message:opacity-100 transition-opacity duration-150">
                <button
                  className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors press"
                  onClick={handleCopy}
                  title="复制"
                >
                  {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
                </button>
                <button
                  className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors press"
                  onClick={() => {
                    if (onRegenerate) onRegenerate();
                    else showToast('重新生成功能即将开放', 'info');
                  }}
                  title="重新生成"
                >
                  <RefreshCw className="h-3.5 w-3.5" />
                </button>
                <button
                  className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-green-600 transition-colors press"
                  onClick={() => handleFeedback('up')}
                  title="有用"
                >
                  <ThumbsUp className="h-3.5 w-3.5" />
                </button>
                <button
                  className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-destructive transition-colors press"
                  onClick={() => handleFeedback('down')}
                  title="没用"
                >
                  <ThumbsDown className="h-3.5 w-3.5" />
                </button>
              </div>
            )}
          </div>
        ) : isStreaming ? (
          <div className="flex items-center gap-2 text-muted-foreground py-2 pl-1">
            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 typing-dot" />
            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 typing-dot" style={{ animationDelay: '0.15s' }} />
            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/60 typing-dot" style={{ animationDelay: '0.3s' }} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

// 导出 key 生成辅助
export function makeMsgKey(msg: ApiChatMessage, idx: number): string {
  return `${msg.role}-${idx}-${mid()}`;
}
