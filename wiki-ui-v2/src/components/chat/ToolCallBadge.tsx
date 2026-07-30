/**
 * ToolCallBadge — 工具调用状态徽标
 *
 * 展示 search_wiki / read_page 等工具的调用过程，默认折叠一行，点击展开。
 */

import { useState } from 'react';
import { ChevronDown, ChevronRight, Search, FileText, Wrench, CheckCircle2, Loader2 } from 'lucide-react';

export type ToolStatus = 'running' | 'done' | 'error';

export interface ToolCallInfo {
  id: string;
  name: string;
  input: Record<string, unknown>;
  output?: string;
  status: ToolStatus;
  error?: string;
}

const toolMeta: Record<string, { icon: typeof Search; label: string; color: string }> = {
  search_wiki: { icon: Search, label: '搜索知识库', color: 'text-blue-500' },
  read_page: { icon: FileText, label: '读取页面', color: 'text-emerald-500' },
  query_graph: { icon: Wrench, label: '查询图谱', color: 'text-purple-500' },
};

const getMeta = (name: string) => toolMeta[name] || { icon: Wrench, label: name, color: 'text-muted-foreground' };

function truncate(s: string, n: number) { return s.length > n ? s.slice(0, n) + '…' : s; }
function prettyInput(input: Record<string, unknown>): string {
  try {
    const v = input.query ?? input.path ?? input.keyword ?? Object.values(input)[0];
    return typeof v === 'string' ? v : JSON.stringify(v);
  } catch { return ''; }
}

export default function ToolCallBadge({ tool }: { tool: ToolCallInfo }) {
  const [open, setOpen] = useState(false);
  const { icon: Icon, label, color } = getMeta(tool.name);
  const summary = prettyInput(tool.input);

  return (
    <div className="my-1.5 text-xs border border-border rounded-md bg-muted/30 overflow-hidden">
      <button
        className="w-full flex items-center gap-2 px-2.5 py-1.5 hover:bg-muted/50 transition-colors text-left"
        onClick={() => setOpen(!open)}
      >
        {open ? <ChevronDown className="h-3 w-3 flex-shrink-0 opacity-60" /> : <ChevronRight className="h-3 w-3 flex-shrink-0 opacity-60" />}
        {tool.status === 'running' ? (
          <Loader2 className={`h-3.5 w-3.5 flex-shrink-0 animate-spin ${color}`} />
        ) : tool.status === 'error' ? (
          <Wrench className={`h-3.5 w-3.5 flex-shrink-0 text-destructive`} />
        ) : (
          <CheckCircle2 className={`h-3.5 w-3.5 flex-shrink-0 ${color}`} />
        )}
        <Icon className={`h-3.5 w-3.5 flex-shrink-0 ${color}`} />
        <span className="font-medium text-foreground/90">{label}</span>
        {summary && <span className="opacity-70 truncate">{truncate(summary, 60)}</span>}
        {tool.status === 'running' && <span className="opacity-50 ml-auto">运行中…</span>}
      </button>
      {open && (
        <div className="px-2.5 pb-2 pt-0.5 border-t border-border/60 bg-background/50 space-y-1.5">
          <div>
            <div className="text-[10px] uppercase tracking-wide opacity-50 mt-1 mb-0.5">输入</div>
            <pre className="text-[11px] bg-muted/50 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all">
              {JSON.stringify(tool.input, null, 2)}
            </pre>
          </div>
          {tool.output && (
            <div>
              <div className="text-[10px] uppercase tracking-wide opacity-50 mt-1 mb-0.5">输出</div>
              <pre className="text-[11px] bg-muted/50 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all max-h-48">
                {truncate(tool.output, 1500)}
              </pre>
            </div>
          )}
          {tool.error && (
            <div className="text-destructive">
              <div className="text-[10px] uppercase tracking-wide mt-1 mb-0.5">错误</div>
              <pre className="text-[11px] bg-destructive/10 rounded p-1.5 overflow-x-auto whitespace-pre-wrap">{tool.error}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
