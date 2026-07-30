/**
 * ChatMessage — 单条消息渲染
 *
 * 支持：user / assistant 气泡、内嵌工具调用徽标、Markdown 渲染、复制按钮
 */

import { useState } from 'react';
import { Copy, Check, Sparkles } from 'lucide-react';
import MarkdownRenderer from '@/components/shared/MarkdownRenderer';
import ToolCallBadge from './ToolCallBadge';
import type { ToolCallInfo } from './ToolCallBadge';
import type { ChatMessage as ApiChatMessage } from '@/api/agent';

interface ChatMessageProps {
  message: ApiChatMessage;
  /** 关联的工具调用列表（assistant 消息） */
  toolCalls?: ToolCallInfo[];
  isStreaming?: boolean;
  onCopy?: (content: string) => void;
  onSaveToWiki?: (content: string) => void;
}

function mid() { return Math.random().toString(36).slice(2, 10); }

export default function ChatMessage({
  message, toolCalls, isStreaming, onCopy, onSaveToWiki,
}: ChatMessageProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === 'user';

  const handleCopy = () => {
    if (onCopy) onCopy(message.content);
    else navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  if (isUser) {
    return (
      <div className="flex gap-3 justify-end">
        <div className="max-w-[75%] bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm whitespace-pre-wrap break-words">
          {message.content}
        </div>
        <div className="flex-shrink-0 w-7 h-7 rounded-full bg-secondary text-secondary-foreground flex items-center justify-center text-xs font-medium">
          U
        </div>
      </div>
    );
  }

  // assistant
  const { content } = message;
  return (
    <div className="flex gap-3">
      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-medium">
        AI
      </div>
      <div className="flex-1 min-w-0">
        {/* 工具调用状态徽标 */}
        {toolCalls && toolCalls.length > 0 && (
          <div className="mb-1.5 space-y-1">
            {toolCalls.map(tc => (
              <ToolCallBadge key={tc.id} tool={tc} />
            ))}
          </div>
        )}

        {content ? (
          <div className="space-y-2">
            <MarkdownRenderer content={content} />
            {!isStreaming && (
              <div className="flex gap-3 pt-1">
                <button
                  className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                  onClick={handleCopy}
                >
                  {copied ? <Check className="h-3 w-3 text-green-500" /> : <Copy className="h-3 w-3" />}
                  {copied ? '已复制' : '复制'}
                </button>
                {onSaveToWiki && (
                  <button
                    className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
                    onClick={() => onSaveToWiki(content)}
                  >
                    <Sparkles className="h-3 w-3" /> 保存到 Wiki
                  </button>
                )}
              </div>
            )}
          </div>
        ) : isStreaming ? (
          <div className="flex items-center gap-2 text-muted-foreground py-1">
            <span className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" />
            <span className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" style={{ animationDelay: '0.2s' }} />
            <span className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" style={{ animationDelay: '0.4s' }} />
          </div>
        ) : null}
      </div>
    </div>
  );
}

// 导出 key 生成辅助（ChatPage 用）
export function makeMsgKey(msg: ApiChatMessage, idx: number): string {
  return `${msg.role}-${idx}-${mid()}`;
}
